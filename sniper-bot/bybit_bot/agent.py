"""Agente Bybit: compra o dip em tokens em alta forte, com TP/SL e alavancagem.

Uso:
    # SIMULA (mostra o que faria, não envia ordem, não precisa de chave):
    python -m bybit_bot.agent --dry-run

    # REAL (na subconta; exige BYBIT_API_KEY/SECRET no .env). Comece em testnet:
    python -m bybit_bot.agent
"""

from __future__ import annotations

import argparse
import logging
import time

from . import indicators, journal, market
from .config import BybitConfig
from .screener import find_candidates
from .trader import make_client, open_long, open_symbols

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("bybit_bot.agent")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Agente Bybit (dip em alta)")
    p.add_argument("--dry-run", action="store_true", help="Não envia ordens; só mostra os candidatos.")
    p.add_argument("--once", action="store_true", help="Roda uma vez e sai (útil para teste).")
    p.add_argument("--symbol", help="Testa abrir 1 long neste par (ex.: BTC/USDT:USDT), pulando o rastreador.")
    return p.parse_args()


def run(cfg: BybitConfig, dry_run: bool, once: bool, symbol: str | None = None) -> int:
    ex = make_client(cfg) if not dry_run else _public_client()

    # Modo teste de conexão: abre uma posição num par específico e sai.
    if symbol:
        log.warning("TESTE de ordem no par %s (%s)...", symbol,
                    "dry-run" if dry_run else "ENVIO REAL")
        if dry_run:
            log.info("[dry-run] abriria LONG em %s.", symbol)
            return 0
        res = open_long(ex, cfg, symbol)
        log.warning("ABRIU %s | entry~%.8f TP=%.8f SL=%.8f | id=%s",
                    res["symbol"], res["entry"], res["tp"], res["sl"], res["order_id"])
        return 0
    env = "TESTNET" if cfg.use_testnet else "REAL (dinheiro de verdade)"
    modo = "DRY-RUN (sem ordens)" if dry_run else f"LIVE | {env}"
    log.warning("Agente Bybit | %s | margem=%s USDT | lev=%dx | TP=+%.0f%% SL=-%.0f%% ROI | máx pos=%d",
                modo, cfg.margin_usdt, cfg.leverage, cfg.tp_roi * 100, cfg.sl_roi * 100,
                cfg.max_positions)
    if not dry_run and cfg.use_market_filter:
        log.warning("Filtro de mercado LIGADO: pausa compras se BTC < %.0f%% 24h ou "
                    "amplitude < %.0f%%.", cfg.btc_min_24h * 100, cfg.breadth_min * 100)
    if not dry_run:
        log.warning("Cooldown por token: %.0f min sem re-entrar após fechar. Filtro técnico: %s.",
                    cfg.cooldown_sec / 60, "RSI+EMA" if cfg.use_ta_filter else "desligado")

    if not dry_run:
        log.warning("Bloqueio de veneno: após %d perdas seguidas, token fica %.0fh de fora.",
                    cfg.max_consec_losses, cfg.block_sec / 3600)

    loops = 0
    cooldowns: dict[str, float] = {}    # símbolo -> epoch do último fechamento
    blocked_until: dict[str, float] = {}  # símbolo -> epoch até quando fica bloqueado
    prev_held: set[str] = set()
    while True:
        try:
            loops += 1
            now = time.time()
            if not dry_run and cfg.autotune and loops % 30 == 1:
                _maybe_autotune(ex, cfg)
            held = set() if dry_run else open_symbols(ex)
            # detecta o que fechou desde o último ciclo -> cooldown + reavalia bloqueios
            closed_now = prev_held - held
            for s in closed_now:
                cooldowns[s] = now
                log.info("Fechou %s — cooldown de %.0f min.", s, cfg.cooldown_sec / 60)
            if not dry_run and (closed_now or loops == 1):
                _refresh_blocklist(ex, cfg, blocked_until, now)
            prev_held = held

            if not dry_run and len(held) >= cfg.max_positions:
                log.info("Já há %d posição(ões) aberta(s); aguardando fechar (TP/SL).", len(held))
            else:
                cands = find_candidates(ex, cfg)
                cands = [c for c in cands if c["symbol"] not in held
                         and now - cooldowns.get(c["symbol"], 0) >= cfg.cooldown_sec
                         and now >= blocked_until.get(c["symbol"], 0)]
                if not cands:
                    log.info("Nenhum candidato agora.")
                elif dry_run:
                    log.info("[dry-run] abriria LONG em %s (não enviei ordem).", cands[0]["symbol"])
                elif cfg.use_market_filter and not (reg := market.evaluate(ex, cfg))["ok"]:
                    log.warning("PAUSA (mercado): %s — não vou abrir agora.", reg["reason"])
                else:
                    _try_open(ex, cfg, cands)
        except KeyboardInterrupt:
            log.info("Interrompido. Tchau!")
            return 0
        except Exception as exc:  # noqa: BLE001
            log.error("Erro no loop (segue tentando): %s", exc)
        if once:
            return 0
        time.sleep(cfg.poll_interval_sec)


def _try_open(ex, cfg, cands: list[dict]) -> None:
    """Abre o primeiro candidato que passar no filtro técnico (RSI+EMA)."""
    for c in cands:
        sym = c["symbol"]
        log.warning("CANDIDATO: %s | 24h +%.0f%% | dip -%.1f%%",
                    sym, c["pct_24h"] * 100, c["dip"] * 100)
        if cfg.use_ta_filter:
            ta = indicators.evaluate(ex, sym, cfg)
            if not ta["ok"]:
                log.info("PULA %s (técnico): %s", sym, ta["reason"])
                continue
        try:
            res = open_long(ex, cfg, sym)
            log.warning("ABRIU %s | entry~%.8f TP=%.8f SL=%.8f | id=%s",
                        res["symbol"], res["entry"], res["tp"], res["sl"], res["order_id"])
            journal.record_open({
                "ts": int(time.time() * 1000), "symbol": res["symbol"],
                "entry": res["entry"], "tp": res["tp"], "sl": res["sl"],
                "pct_24h": c["pct_24h"], "dip": c["dip"], "qty": res["qty"],
            })
            return
        except Exception as exc:  # noqa: BLE001
            log.error("Falha ao abrir %s: %s", sym, exc)
    log.info("Nenhum candidato passou nos filtros agora.")


def _refresh_blocklist(ex, cfg, blocked_until: dict, now: float) -> None:
    """Bloqueia tokens com N+ perdas seguidas recentes (os 'veneno')."""
    streaks = journal.tail_loss_streaks(journal.fetch_closed(ex, limit=50))
    for sym, n in streaks.items():
        if n >= cfg.max_consec_losses and now >= blocked_until.get(sym, 0):
            blocked_until[sym] = now + cfg.block_sec
            log.warning("BLOQUEIO: %s (%d perdas seguidas) fica %.0fh de fora.",
                        sym, n, cfg.block_sec / 3600)


def _maybe_autotune(ex, cfg) -> None:
    """Ajusta dip_min com base no histórico (só se houver amostra suficiente)."""
    closed = journal.fetch_closed(ex)
    if len(closed) < cfg.autotune_min_trades:
        log.info("Autotune aguardando amostra: %d/%d trades fechados.",
                 len(closed), cfg.autotune_min_trades)
        return
    novo = journal.suggest_dip_min(closed, journal.load_opens(), cfg)
    if novo and abs(novo - cfg.dip_min) >= 0.005:
        log.warning("AUTOTUNE: ajustando dip_min de %.1f%% para %.1f%% (com base em %d trades).",
                    cfg.dip_min * 100, novo * 100, len(closed))
        cfg.dip_min = novo


def _public_client():
    import ccxt
    return ccxt.bybit({"options": {"defaultType": "swap"}, "enableRateLimit": True})


def main() -> int:
    args = parse_args()
    try:
        cfg = BybitConfig.load()
        if not args.dry_run:
            cfg.require_keys()
    except ValueError as exc:
        log.error("%s", exc)
        return 2
    return run(cfg, args.dry_run, args.once, args.symbol)


if __name__ == "__main__":
    import sys
    sys.exit(main())
