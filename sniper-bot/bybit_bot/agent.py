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

from . import brain, indicators, journal, market
from .config import BybitConfig
from .screener import find_candidates, find_top_gainer
from .status import fetch_balance_usdt
from .trader import (add_long, close_position, dca_decision, make_client,
                     open_long, open_symbols, position_detail)

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
    if cfg.dca_enabled:
        log.warning("ESTRATÉGIA DCA (preço médio) na moeda #1 em alta 24h | entrada=%.2f USDT x %dx | "
                    "reforço a cada -%.0f%% ROI (até %dx) | TP +%.0f%% ROI sobre a média | "
                    "stop após os reforços.", cfg.margin_usdt, cfg.leverage,
                    cfg.dca_trigger_roi * 100, cfg.dca_max, cfg.tp_roi * 100)
        log.warning("Entrada só quando a TOP-1 estiver num dip de %.0f-%.0f%% (candles de %s).",
                    cfg.dip_min * 100, cfg.dip_max * 100, cfg.screen_timeframe)
    else:
        log.warning("Universo: perps em alta 24h de +%.0f%% a +%.0f%% | dip %.0f-%.0f%% em candles de %s.",
                    cfg.min_24h * 100, cfg.max_24h * 100, cfg.dip_min * 100, cfg.dip_max * 100,
                    cfg.screen_timeframe)
    if not dry_run and cfg.use_market_filter:
        log.warning("Filtro de mercado LIGADO: pausa compras se BTC < %.0f%% 24h ou "
                    "amplitude < %.0f%%.", cfg.btc_min_24h * 100, cfg.breadth_min * 100)
    if not dry_run:
        log.warning("Cooldown por token: %.0f min sem re-entrar após fechar. Filtro técnico: %s.",
                    cfg.cooldown_sec / 60, "RSI+EMA" if cfg.use_ta_filter else "desligado")

    if not dry_run:
        log.warning("Bloqueio de veneno: após %d perdas seguidas, token fica %.0fh de fora.",
                    cfg.max_consec_losses, cfg.block_sec / 3600)
    if not dry_run and cfg.brain_enabled:
        log.warning("CÉREBRO ligado: reduz margem se PF<%.1f, pausa se PF<%.1f ou %d perdas "
                    "seguidas, e disjuntor se saldo cair >%.0f%%.", cfg.brain_reduce_pf,
                    cfg.brain_pause_pf, cfg.brain_pause_streak, cfg.brain_max_dd * 100)

    loops = 0
    cooldowns: dict[str, float] = {}    # símbolo -> epoch do último fechamento
    blocked_until: dict[str, float] = {}  # símbolo -> epoch até quando fica bloqueado
    prev_held: set[str] = set()
    peak_ref = [0.0]                     # topo do saldo (para o disjuntor de drawdown)
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

            if cfg.dca_enabled:
                _dca_cycle(ex, cfg, held, cooldowns, now, dry_run)
            elif not dry_run and len(held) >= cfg.max_positions:
                log.info("Já há %d posição(ões) aberta(s); aguardando fechar (TP/SL).", len(held))
            else:
                allowed, margin, reason = _brain_gate(ex, cfg, peak_ref, dry_run)
                if not allowed:
                    log.warning("CÉREBRO: %s — sem novas entradas agora.", reason)
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
                        if margin < cfg.margin_usdt:
                            log.warning("CÉREBRO: %s — margem reduzida p/ %.1f USDT.", reason, margin)
                        _try_open(ex, cfg, cands, margin)
        except KeyboardInterrupt:
            log.info("Interrompido. Tchau!")
            return 0
        except Exception as exc:  # noqa: BLE001
            log.error("Erro no loop (segue tentando): %s", exc)
        if once:
            return 0
        time.sleep(cfg.poll_interval_sec)


def _brain_gate(ex, cfg, peak_ref: list, dry_run: bool):
    """Consulta o cérebro: (pode_abrir, margem_efetiva, motivo)."""
    if dry_run or not cfg.brain_enabled:
        return True, cfg.margin_usdt, "cérebro off"
    recent = [c["pnl"] for c in journal.fetch_closed(ex, limit=cfg.brain_window)]
    dec = brain.decide(recent, cfg)
    total, _ = fetch_balance_usdt(ex)
    if total > peak_ref[0]:
        peak_ref[0] = total
    if not brain.drawdown_ok(total, peak_ref[0], cfg.brain_max_dd):
        return (False, 0.0, f"disjuntor: saldo {total:.2f} caiu >{cfg.brain_max_dd * 100:.0f}% "
                f"do topo {peak_ref[0]:.2f}")
    if not dec["open_allowed"]:
        return False, 0.0, dec["reason"]
    return True, cfg.margin_usdt * dec["margin_mult"], dec["reason"]


def _try_open(ex, cfg, cands: list[dict], margin: float | None = None) -> None:
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
            res = open_long(ex, cfg, sym, margin_usdt=margin)
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


def _dca_cycle(ex, cfg, held: set, cooldowns: dict, now: float, dry_run: bool) -> None:
    """Estratégia DCA: mira a moeda #1 em alta 24h; entra no dip e reforça se cair.

    Se já há posição, gerencia (reforça / TP / stop). Senão, procura a TOP-1 e só
    abre quando ela estiver num pequeno dip e passar nos filtros.
    """
    if dry_run:
        top = find_top_gainer(ex, cfg)
        if top:
            tag = "ENTRARIA (no dip)" if top["dipping"] else "esperando dip"
            log.info("[dry-run] TOP-1 24h: %s +%.0f%% | dip -%.1f%% | %s",
                     top["symbol"], top["pct_24h"] * 100, top["dip"] * 100, tag)
        return

    if held:                                   # já temos posição: gerenciar
        for sym in list(held):
            _manage_dca(ex, cfg, sym)
        return

    top = find_top_gainer(ex, cfg)             # sem posição: caçar a TOP-1
    if not top:
        log.info("Sem dados de alta 24h agora.")
        return
    sym = top["symbol"]
    if not top["dipping"]:
        log.info("TOP-1 alta 24h: %s +%.0f%% (dip -%.1f%%) — esperando o dip de %.0f-%.0f%%.",
                 sym, top["pct_24h"] * 100, top["dip"] * 100, cfg.dip_min * 100, cfg.dip_max * 100)
        return
    log.warning("TOP-1 no dip: %s | 24h +%.0f%% | dip -%.1f%%",
                sym, top["pct_24h"] * 100, top["dip"] * 100)
    if now - cooldowns.get(sym, 0) < cfg.cooldown_sec:
        log.info("%s em cooldown (%.0f min) — não reentro agora.", sym, cfg.cooldown_sec / 60)
        return
    if cfg.use_market_filter and not (reg := market.evaluate(ex, cfg))["ok"]:
        log.warning("PAUSA (mercado): %s — não vou abrir agora.", reg["reason"])
        return
    if cfg.use_ta_filter:
        ta = indicators.evaluate(ex, sym, cfg)
        if not ta["ok"]:
            log.info("PULA %s (técnico): %s", sym, ta["reason"])
            return
    try:
        res = add_long(ex, cfg, sym)
        log.warning("ABRIU base DCA %s | entry~%.8f | margem=%.2f USDT", sym, res["price"], cfg.margin_usdt)
        journal.record_open({
            "ts": int(time.time() * 1000), "symbol": sym, "entry": res["price"],
            "tp": 0.0, "sl": 0.0, "pct_24h": top["pct_24h"], "dip": top["dip"],
            "qty": res["qty"],
        })
    except Exception as exc:  # noqa: BLE001
        log.error("Falha ao abrir %s: %s", sym, exc)


def _manage_dca(ex, cfg, symbol: str) -> None:
    """Gerencia a posição aberta no modo DCA: reforça, realiza (TP) ou corta (stop)."""
    det = position_detail(ex, cfg, symbol)
    if not det or det["margin"] <= 0:
        return
    roi = det["pnl"] / det["margin"]
    adds_done = max(0, round(det["margin"] / cfg.margin_usdt) - 1)
    action = dca_decision(roi, adds_done, cfg.tp_roi, cfg.dca_trigger_roi, cfg.dca_max)
    if action == "tp":
        log.warning("TP: %s ROI %+.0f%% (média) — realizo tudo (P&L %+.2f USDT).",
                    symbol, roi * 100, det["pnl"])
        close_position(ex, symbol)
    elif action == "dca":
        log.warning("DCA %d/%d: %s ROI %+.0f%% — reforço +%.2f USDT (baixa o preço médio).",
                    adds_done + 1, cfg.dca_max, symbol, roi * 100, cfg.margin_usdt)
        try:
            add_long(ex, cfg, symbol)
        except Exception as exc:  # noqa: BLE001
            log.error("Falha no reforço DCA de %s: %s", symbol, exc)
    elif action == "stop":
        log.warning("STOP: %s ROI %+.0f%% após %d reforços — corto a perda (P&L %+.2f USDT).",
                    symbol, roi * 100, adds_done, det["pnl"])
        close_position(ex, symbol)
    else:
        log.info("Segurando %s | ROI %+.0f%% | reforços %d/%d | margem %.2f | P&L %+.2f",
                 symbol, roi * 100, adds_done, cfg.dca_max, det["margin"], det["pnl"])


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
