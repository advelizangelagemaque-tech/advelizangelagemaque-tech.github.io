"""Loop principal do sniper bot.

Uso:
    python -m sniper.main            # roda (testnet se USE_TESTNET=true)
    python -m sniper.main --dry-run  # simula, não envia ordens
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from .client import make_client
from .config import Config
from .detector import ListingDetector
from .trader import Trader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("sniper.main")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Sniper de listagens — Binance Futures")
    p.add_argument("--dry-run", action="store_true", help="Não envia ordens; apenas simula.")
    p.add_argument("--side", choices=["BUY", "SELL"], default="BUY",
                   help="Direção da entrada (default: BUY/long).")
    return p.parse_args()


def run(cfg: Config, dry_run: bool, side: str) -> None:
    client = make_client(cfg.api_key, cfg.api_secret, cfg.use_testnet)
    detector = ListingDetector(cfg.quote_asset)
    trader = Trader(client, cfg, dry_run=dry_run)

    mode = "DRY-RUN" if dry_run else ("TESTNET" if cfg.use_testnet else "PRODUÇÃO (REAL)")
    log.warning("Iniciando sniper | modo=%s | quote=%s | margem=%s USDT | lev=%dx",
                mode, cfg.quote_asset, cfg.margin_usdt, cfg.leverage)
    if not cfg.use_testnet and not dry_run:
        log.warning(">>> ATENÇÃO: rodando com DINHEIRO REAL. <<<")

    # Snapshot inicial (não snipa o que já existe).
    detector.prime(client.exchange_info())

    interval = cfg.poll_interval_ms / 1000.0
    trades_done = 0

    while True:
        try:
            new_symbols = detector.detect_new(client.exchange_info())
            for sym in new_symbols:
                log.warning("NOVA LISTAGEM detectada: %s", sym.symbol)
                try:
                    trader.snipe(sym, side=side)
                    trades_done += 1
                except Exception as exc:  # noqa: BLE001
                    log.error("Falha ao snipar %s: %s", sym.symbol, exc)
                if cfg.max_trades and trades_done >= cfg.max_trades:
                    log.warning("MAX_TRADES (%d) atingido. Encerrando.", cfg.max_trades)
                    return
            time.sleep(interval)
        except KeyboardInterrupt:
            log.info("Interrompido pelo usuário. Tchau!")
            return
        except Exception as exc:  # noqa: BLE001
            # Erros de rede/rate-limit não devem derrubar o bot.
            log.error("Erro no loop (segue tentando): %s", exc)
            time.sleep(max(interval, 1.0))


def main() -> int:
    args = parse_args()
    try:
        cfg = Config.load()
    except ValueError as exc:
        log.error("%s", exc)
        return 2
    run(cfg, dry_run=args.dry_run, side=args.side)
    return 0


if __name__ == "__main__":
    sys.exit(main())
