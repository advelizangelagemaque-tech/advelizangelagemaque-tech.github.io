"""Loop principal do sniper bot.

Exemplos:
    python -m sniper.main --paper --mode ws     # paper-trading via WebSocket (recomendado p/ validar)
    python -m sniper.main --paper --mode poll   # paper-trading via REST polling
    python -m sniper.main --dry-run             # só mostra a intenção, não registra nada
    python -m sniper.main                        # LIVE (testnet se USE_TESTNET=true)
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from .client import make_client
from .config import Config
from .detector import PollDetector
from .journal import Journal
from .quality import check_quality
from .trader import Trader
from .ws_detector import WSDetector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("sniper.main")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Sniper de listagens — Binance Futures")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--paper", action="store_true", help="Paper-trading: simula e mede resultado.")
    g.add_argument("--dry-run", action="store_true", help="Só loga a intenção; não registra nada.")
    p.add_argument("--mode", choices=["poll", "ws"], default="poll",
                   help="Detecção por REST polling (poll) ou WebSocket (ws).")
    p.add_argument("--side", choices=["BUY", "SELL"], default="BUY",
                   help="Direção da entrada (default: BUY/long).")
    p.add_argument("--journal", default="trades.csv", help="Arquivo CSV do diário.")
    return p.parse_args()


def resolve_paper_positions(book: list[dict], trader: Trader, journal: Journal) -> None:
    """Acompanha posições de paper-trading e fecha quando bate TP ou SL."""
    for trade in list(book):
        try:
            price = trader.get_mark_price(trade["symbol"])
        except Exception as exc:  # noqa: BLE001
            log.error("Não consegui obter preço de %s: %s", trade["symbol"], exc)
            continue

        long = trade["side"] == "BUY"
        hit_tp = price >= trade["tp"] if long else price <= trade["tp"]
        hit_sl = price <= trade["sl"] if long else price >= trade["sl"]
        if not (hit_tp or hit_sl):
            continue

        exit_price = trade["tp"] if hit_tp else trade["sl"]
        sign = 1 if long else -1
        pnl_usdt = trade["qty"] * (exit_price - trade["entry"]) * sign
        pnl_pct = pnl_usdt / trade["margin_usdt"] if trade["margin_usdt"] else 0.0
        status = "WIN" if hit_tp else "LOSS"
        journal.record_close(trade, "paper", exit_price, pnl_usdt, pnl_pct, status)
        log.warning("[paper] %s fechou %s | exit=%.6f PnL=%.4f USDT (%.2f%% da margem)",
                    trade["symbol"], status, exit_price, pnl_usdt, pnl_pct * 100)
        book.remove(trade)


def run(cfg: Config, mode_trade: str, detect_mode: str, side: str, journal_path: str) -> None:
    client = make_client(cfg.api_key, cfg.api_secret, cfg.use_testnet)
    trader = Trader(client, cfg, mode=mode_trade)
    journal = None if mode_trade == "dry" else Journal(journal_path)
    detector = (WSDetector if detect_mode == "ws" else PollDetector)(client, cfg.quote_asset)

    env = "TESTNET" if cfg.use_testnet else "PRODUÇÃO (REAL)"
    log.warning("Sniper | trade=%s | detecção=%s | ambiente=%s | quote=%s | margem=%s USDT | lev=%dx",
                mode_trade, detect_mode, env, cfg.quote_asset, cfg.margin_usdt, cfg.leverage)
    if cfg.use_testnet is False and mode_trade == "live":
        log.warning(">>> ATENÇÃO: ordens com DINHEIRO REAL. <<<")

    detector.start()
    interval = cfg.poll_interval_ms / 1000.0
    paper_book: list[dict] = []
    trades_done = 0

    try:
        while True:
            try:
                for sym in detector.poll():
                    log.warning("NOVA LISTAGEM: %s", sym.symbol)

                    # Filtro de qualidade: liquidez/spread antes de entrar.
                    try:
                        ok, reason, metrics = check_quality(client, sym, cfg)
                    except Exception as exc:  # noqa: BLE001
                        ok, reason, metrics = False, f"erro ao avaliar qualidade: {exc}", {}
                    if not ok:
                        log.warning("PULANDO %s — %s | métricas=%s", sym.symbol, reason, metrics)
                        if journal:
                            journal.record_skip(sym.symbol, mode_trade, reason)
                        continue
                    log.info("Qualidade OK para %s | %s", sym.symbol, metrics)

                    try:
                        trade = trader.snipe(sym, side=side)
                    except Exception as exc:  # noqa: BLE001
                        log.error("Falha ao snipar %s: %s", sym.symbol, exc)
                        continue
                    if trade is None:
                        continue
                    if journal:
                        journal.record_open(trade, mode_trade)
                    if mode_trade == "paper":
                        paper_book.append(trade)
                    trades_done += 1
                    if cfg.max_trades and trades_done >= cfg.max_trades and not paper_book:
                        log.warning("MAX_TRADES (%d) atingido. Encerrando.", cfg.max_trades)
                        return

                if mode_trade == "paper":
                    resolve_paper_positions(paper_book, trader, journal)

                # Encerra quando atingiu o limite e não há mais paper aberto.
                if cfg.max_trades and trades_done >= cfg.max_trades and not paper_book:
                    log.warning("MAX_TRADES (%d) atingido e sem posições abertas. Encerrando.",
                                cfg.max_trades)
                    return

                time.sleep(interval)
            except KeyboardInterrupt:
                raise
            except Exception as exc:  # noqa: BLE001
                log.error("Erro no loop (segue tentando): %s", exc)
                time.sleep(max(interval, 1.0))
    except KeyboardInterrupt:
        log.info("Interrompido pelo usuário. Tchau!")
    finally:
        detector.stop()


def main() -> int:
    args = parse_args()
    mode_trade = "paper" if args.paper else ("dry" if args.dry_run else "live")
    try:
        cfg = Config.load()
    except ValueError as exc:
        log.error("%s", exc)
        return 2
    run(cfg, mode_trade, args.mode, args.side, args.journal)
    return 0


if __name__ == "__main__":
    sys.exit(main())
