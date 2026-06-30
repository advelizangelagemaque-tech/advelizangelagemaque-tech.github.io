"""Resumo de desempenho a partir do diário CSV.

Uso:
    python -m sniper.summary               # lê trades.csv
    python -m sniper.summary trades.csv    # caminho explícito
"""

from __future__ import annotations

import csv
import sys


def summarize(path: str = "trades.csv") -> dict:
    wins, losses, skipped, opens = [], [], 0, 0
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            status = (row.get("status") or "").upper()
            if status == "WIN":
                wins.append(float(row.get("pnl_usdt") or 0))
            elif status == "LOSS":
                losses.append(float(row.get("pnl_usdt") or 0))
            elif status == "SKIPPED":
                skipped += 1
            elif status == "OPEN":
                opens += 1

    closed = len(wins) + len(losses)
    gross_win = sum(wins)
    gross_loss = sum(losses)  # já é negativo
    total_pnl = gross_win + gross_loss
    win_rate = len(wins) / closed if closed else 0.0
    expectancy = total_pnl / closed if closed else 0.0
    profit_factor = (gross_win / abs(gross_loss)) if gross_loss else float("inf")

    return {
        "closed": closed, "wins": len(wins), "losses": len(losses),
        "open": opens, "skipped": skipped,
        "win_rate": win_rate, "total_pnl": total_pnl,
        "avg_win": gross_win / len(wins) if wins else 0.0,
        "avg_loss": gross_loss / len(losses) if losses else 0.0,
        "expectancy": expectancy, "profit_factor": profit_factor,
    }


def _fmt(s: dict) -> str:
    pf = "∞" if s["profit_factor"] == float("inf") else f"{s['profit_factor']:.2f}"
    return (
        "===== RESUMO DO DIÁRIO =====\n"
        f"Trades fechados : {s['closed']}  (WIN {s['wins']} / LOSS {s['losses']})\n"
        f"Abertos         : {s['open']}\n"
        f"Pulados (filtro): {s['skipped']}\n"
        f"Taxa de acerto  : {s['win_rate']:.1%}\n"
        f"PnL total       : {s['total_pnl']:+.4f} USDT\n"
        f"Média ganho     : {s['avg_win']:+.4f} USDT\n"
        f"Média perda     : {s['avg_loss']:+.4f} USDT\n"
        f"Expectativa/tr. : {s['expectancy']:+.4f} USDT\n"
        f"Profit factor   : {pf}\n"
        "============================"
    )


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else "trades.csv"
    try:
        print(_fmt(summarize(path)))
    except FileNotFoundError:
        print(f"Diário não encontrado: {path}. Rode o bot em --paper primeiro.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
