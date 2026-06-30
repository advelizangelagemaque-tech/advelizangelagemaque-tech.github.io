"""Diário de operações em CSV — registra cada entrada e seu desfecho.

Serve tanto para paper-trading quanto para operações reais, permitindo
medir o desempenho da estratégia antes (e depois) de arriscar capital.
"""

from __future__ import annotations

import csv
import logging
import os
from datetime import datetime, timezone

log = logging.getLogger("sniper.journal")

FIELDS = [
    "timestamp", "mode", "symbol", "side", "qty",
    "entry", "tp", "sl", "status", "exit_price",
    "pnl_usdt", "pnl_pct", "note",
]


class Journal:
    """Acrescenta linhas num CSV. Cada trade vira uma linha (OPEN -> WIN/LOSS)."""

    def __init__(self, path: str = "trades.csv"):
        self.path = path
        if not os.path.exists(path):
            with open(path, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(FIELDS)
            log.info("Diário criado em %s", os.path.abspath(path))

    def _row(self, **kw) -> None:
        kw.setdefault("timestamp", datetime.now(timezone.utc).isoformat(timespec="seconds"))
        with open(self.path, "a", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=FIELDS).writerow({k: kw.get(k, "") for k in FIELDS})

    def record_open(self, trade: dict, mode: str) -> None:
        self._row(
            mode=mode, symbol=trade["symbol"], side=trade["side"], qty=trade["qty"],
            entry=trade["entry"], tp=trade["tp"], sl=trade["sl"],
            status="OPEN", note="entrada registrada",
        )

    def record_close(self, trade: dict, mode: str, exit_price: float,
                     pnl_usdt: float, pnl_pct: float, status: str) -> None:
        self._row(
            mode=mode, symbol=trade["symbol"], side=trade["side"], qty=trade["qty"],
            entry=trade["entry"], tp=trade["tp"], sl=trade["sl"],
            status=status, exit_price=exit_price,
            pnl_usdt=round(pnl_usdt, 6), pnl_pct=round(pnl_pct, 4),
            note="posição encerrada",
        )
