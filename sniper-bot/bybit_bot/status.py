"""Status da subconta Bybit: saldo + posições abertas (com TP/SL e lucro).

Como a subconta de IA tem "login restrito" (só API), esta é a forma de ver o
que está acontecendo — direto do servidor, sem depender do app.

    python -m bybit_bot.status
"""

from __future__ import annotations

import logging

from .config import BybitConfig
from .trader import make_client

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("bybit_bot.status")


def _num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def fetch_balance_usdt(ex) -> tuple[float, float]:
    """(total, livre) em USDT da conta que a chave enxerga."""
    try:
        bal = ex.fetch_balance()
    except Exception as exc:  # noqa: BLE001
        log.warning("Não consegui ler o saldo: %s", exc)
        return 0.0, 0.0
    usdt = bal.get("USDT", {})
    return _num(usdt.get("total")), _num(usdt.get("free"))


def fetch_open_positions(ex) -> list[dict]:
    """Posições abertas normalizadas (symbol, side, entry, mark, pnl, tp, sl)."""
    try:
        positions = ex.fetch_positions()
    except Exception as exc:  # noqa: BLE001
        log.warning("Não consegui ler posições: %s", exc)
        return []
    out = []
    for p in positions:
        contracts = _num(p.get("contracts") or p.get("contractSize"))
        if contracts == 0:
            continue
        info = p.get("info", {}) or {}
        out.append({
            "symbol": p.get("symbol"),
            "side": p.get("side"),
            "contracts": contracts,
            "entry": _num(p.get("entryPrice") or info.get("avgPrice")),
            "mark": _num(p.get("markPrice") or info.get("markPrice")),
            "pnl": _num(p.get("unrealizedPnl") or info.get("unrealisedPnl")),
            "tp": info.get("takeProfit") or "-",
            "sl": info.get("stopLoss") or "-",
        })
    return out


def main() -> int:
    cfg = BybitConfig.load()
    cfg.require_keys()
    ex = make_client(cfg)

    env = "TESTNET" if cfg.use_testnet else "REAL"
    total, free = fetch_balance_usdt(ex)
    log.info("=" * 56)
    log.info("SUBCONTA BYBIT (%s)", env)
    log.info("Saldo USDT: total=%.4f | livre=%.4f", total, free)
    log.info("-" * 56)

    positions = fetch_open_positions(ex)
    if not positions:
        log.info("Nenhuma posição aberta agora.")
    else:
        for p in positions:
            log.info("%s  %s  qty=%s", p["symbol"], (p["side"] or "").upper(), p["contracts"])
            log.info("   entrada=%.8f  atual=%.8f", p["entry"], p["mark"])
            log.info("   TP=%s  SL=%s", p["tp"], p["sl"])
            sinal = "+" if p["pnl"] >= 0 else ""
            log.info("   lucro/prejuízo atual: %s%.4f USDT", sinal, p["pnl"])
    log.info("=" * 56)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
