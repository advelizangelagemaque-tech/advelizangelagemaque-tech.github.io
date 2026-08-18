"""Diário de operações: registra cada trade e mostra a verdade nua — taxa de
acerto, resultado acumulado e expectativa. Medir pra SABER, não pra achar.

Guarda tudo em trade_journal.csv (fica só na EC2, fora do git — é seu dado).
O que importa não é ganhar 1 trade; é o resultado ao longo de MUITOS. Este
diário deixa isso visível: com 2 trades você não sabe nada; com 20-30, sabe.
"""

from __future__ import annotations

import argparse
import csv
import os
from datetime import date

JOURNAL_PATH = os.path.join(os.path.dirname(__file__), "..", "trade_journal.csv")
FIELDS = ["data", "symbol", "side", "entry", "exit", "result", "note"]


# ---- lógica pura (testável) ------------------------------------------------

def pnl_pct(side: str, entry: float, exit: float) -> float:
    """Retorno % de um trade. short ganha quando cai; long quando sobe;
    neutro não é direcional (o resultado real vem da coluna 'result')."""
    if entry <= 0 or side == "neutro":
        return 0.0
    if side == "short":
        return (entry - exit) / entry
    return (exit - entry) / entry


def summarize(trades: list[dict]) -> dict:
    """Estatística honesta da lista de trades (usa a coluna 'result' em USDT)."""
    results = []
    for t in trades:
        r = t.get("result")
        if r not in (None, ""):
            try:
                results.append(float(r))
            except ValueError:
                continue
    n = len(results)
    wins = [r for r in results if r > 0]
    losses = [r for r in results if r < 0]
    return {
        "n": n,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / n if n else 0.0,
        "total": sum(results),
        "avg_win": sum(wins) / len(wins) if wins else 0.0,
        "avg_loss": sum(losses) / len(losses) if losses else 0.0,
        "expectancy": sum(results) / n if n else 0.0,
    }


# ---- armazenamento (CSV) ---------------------------------------------------

def load_trades(path: str = JOURNAL_PATH) -> list[dict]:
    try:
        with open(path, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except FileNotFoundError:
        return []


def append_trade(row: dict, path: str = JOURNAL_PATH) -> None:
    exists = os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if not exists:
            w.writeheader()
        w.writerow(row)


# ---- CLI -------------------------------------------------------------------

def _print_stats(trades: list[dict]) -> None:
    s = summarize(trades)
    print("=" * 60)
    print(f"DIÁRIO DE OPERAÇÕES — {s['n']} trade(s) registrados")
    print("=" * 60)
    for t in trades:
        r = float(t["result"]) if t.get("result") not in (None, "") else 0.0
        mark = "✅" if r > 0 else "❌" if r < 0 else "➖"
        print(f"  {t.get('data',''):<10} {t.get('symbol',''):<8} {t.get('side',''):<6} "
              f"{mark} {r:+.2f} USDT   {t.get('note','')}")
    print("-" * 60)
    print(f"Acertos      : {s['wins']} de {s['n']}  ({s['win_rate']*100:.0f}%)")
    print(f"Resultado    : {s['total']:+.2f} USDT no acumulado")
    print(f"Média ganho  : {s['avg_win']:+.2f}   |   Média perda: {s['avg_loss']:+.2f}")
    print(f"Expectativa  : {s['expectancy']:+.2f} USDT por trade")
    print("=" * 60)
    if s["n"] < 20:
        print(f"⚠️  Só {s['n']} trade(s). Ainda é POUCO pra concluir qualquer coisa —")
        print("   deixe chegar a ~20-30 antes de confiar no número. Amostra pequena engana.")
    else:
        veredito = "no lucro 🎉" if s["total"] > 0 else "no prejuízo — repensar"
        print(f"Amostra razoável. No acumulado, a estratégia está {veredito}.")
    print("=" * 60)


def main() -> int:
    p = argparse.ArgumentParser(description="Diário de operações (registra e mede).")
    sub = p.add_subparsers(dest="cmd")

    a = sub.add_parser("add", help="Registra um trade.")
    a.add_argument("symbol", help="Ex: BSP")
    a.add_argument("side", choices=["long", "short", "neutro"])
    a.add_argument("result", type=float, help="Resultado REAL em USDT (o que a Bybit mostrou; use - pra perda).")
    a.add_argument("--entry", type=float, default=None, help="Preço de entrada (opcional, pro registro).")
    a.add_argument("--exit", type=float, default=None, help="Preço de saída (opcional).")
    a.add_argument("--note", default="", help="Anotação (opcional).")
    a.add_argument("--date", default=str(date.today()), help="Data (padrão hoje).")

    sub.add_parser("show", help="Mostra o diário e as estatísticas.")

    args = p.parse_args()
    if args.cmd == "add":
        row = {"data": args.date, "symbol": args.symbol.upper(), "side": args.side,
               "entry": args.entry if args.entry is not None else "",
               "exit": args.exit if args.exit is not None else "",
               "result": args.result, "note": args.note}
        append_trade(row)
        print(f"✅ Registrado: {args.symbol.upper()} {args.side} {args.result:+.2f} USDT")
        _print_stats(load_trades())
        return 0
    _print_stats(load_trades())
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
