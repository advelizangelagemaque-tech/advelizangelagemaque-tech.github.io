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

    while True:
        try:
            held = set() if dry_run else open_symbols(ex)
            if not dry_run and len(held) >= cfg.max_positions:
                log.info("Já há %d posição(ões) aberta(s); aguardando fechar (TP/SL).", len(held))
            else:
                cands = find_candidates(ex, cfg)
                cands = [c for c in cands if c["symbol"] not in held]
                if not cands:
                    log.info("Nenhum candidato agora.")
                else:
                    top = cands[0]
                    log.warning("CANDIDATO: %s | 24h +%.0f%% | dip -%.1f%%",
                                top["symbol"], top["pct_24h"] * 100, top["dip"] * 100)
                    if dry_run:
                        log.info("[dry-run] abriria LONG em %s (não enviei ordem).", top["symbol"])
                    else:
                        try:
                            res = open_long(ex, cfg, top["symbol"])
                            log.warning("ABRIU %s | entry~%.8f TP=%.8f SL=%.8f | id=%s",
                                        res["symbol"], res["entry"], res["tp"], res["sl"],
                                        res["order_id"])
                        except Exception as exc:  # noqa: BLE001
                            log.error("Falha ao abrir %s: %s", top["symbol"], exc)
        except KeyboardInterrupt:
            log.info("Interrompido. Tchau!")
            return 0
        except Exception as exc:  # noqa: BLE001
            log.error("Erro no loop (segue tentando): %s", exc)
        if once:
            return 0
        time.sleep(cfg.poll_interval_sec)


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
