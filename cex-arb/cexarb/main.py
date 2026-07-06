"""CLI do medidor de gap entre corretoras (Fase 0: só mede, não opera)."""

from __future__ import annotations

import argparse


def main() -> int:
    p = argparse.ArgumentParser(
        description="Mede o gap REAL entre duas corretoras (spot, só leitura).")
    p.add_argument("--a", default="bybit", help="Corretora A (padrão: bybit).")
    p.add_argument("--b", default="binance", help="Corretora B (padrão: binance).")
    p.add_argument("--pairs", default="", help="Pares separados por vírgula (ex: BTC/USDT,ETH/USDT).")
    p.add_argument("--fee-a", type=float, default=None, help="Taxa taker de A em fração (0.001 = 0.1%%).")
    p.add_argument("--fee-b", type=float, default=None, help="Taxa taker de B em fração.")
    args = p.parse_args()

    from .scan import scan
    pairs = [s.strip() for s in args.pairs.split(",") if s.strip()] or None
    return scan(ex_a=args.a, ex_b=args.b, pairs=pairs, fee_a=args.fee_a, fee_b=args.fee_b)


if __name__ == "__main__":
    import sys
    sys.exit(main())
