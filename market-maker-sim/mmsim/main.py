"""CLI do simulador de market making (Fase 0: só mede, não opera)."""

from __future__ import annotations

import argparse

from .grid import GridParams, run_grid_demo, simulate_grid
from .mm import MMParams, simulate_mm, summary_pct


def main() -> int:
    p = argparse.ArgumentParser(
        description="Simulador de market making (só mede em candles, não opera).")
    p.add_argument("--demo", action="store_true", help="Roda os cenários de exemplo (sem internet).")
    p.add_argument("--run", metavar="PAR", help="Mede em preços REAIS (ex: BTC/USDT:USDT).")
    p.add_argument("--tf", default="1m", help="Timeframe dos candles (padrão 1m).")
    p.add_argument("--limit", type=int, default=1000, help="Quantos candles (padrão 1000).")
    p.add_argument("--spread-bps", type=float, default=10, help="Spread total em pontos-base (10 = 0.10%%).")
    p.add_argument("--order", type=float, default=20, help="Tamanho de cada ordem em USDT.")
    p.add_argument("--max-inv", type=float, default=100, help="Teto de estoque por lado em USDT.")
    p.add_argument("--fee-bps", type=float, default=2, help="Taxa de maker por execução (padrão 0.02%%).")
    # ---- GRID de futuros ----
    p.add_argument("--grid-demo", action="store_true", help="Demonstra o GRID de futuros (sem internet).")
    p.add_argument("--grid", metavar="PAR", help="Mede o GRID em preços REAIS (ex: SOL/USDT:USDT).")
    p.add_argument("--lower", type=float, help="Piso da faixa do grid (padrão: mínimo recente).")
    p.add_argument("--upper", type=float, help="Teto da faixa do grid (padrão: máximo recente).")
    p.add_argument("--grids", type=int, default=30, help="Número de níveis do grid (padrão 30).")
    p.add_argument("--leverage", type=int, default=2, help="Alavancagem do grid (padrão 2x — BAIXA!).")
    p.add_argument("--capital", type=float, default=100, help="Margem em USDT (padrão 100).")
    args = p.parse_args()

    if args.grid_demo:
        return run_grid_demo()

    if args.grid:
        return _run_grid(args)

    if args.run:
        from .data import fetch_ohlcv
        candles = fetch_ohlcv(args.run, args.tf, args.limit)
        params = MMParams(args.spread_bps, args.order, args.max_inv, args.fee_bps)
        st = simulate_mm(candles, params)
        span_h = len(candles) * (1 if args.tf.endswith("m") else 60) / 60.0
        print("=" * 64)
        print(f"MARKET MAKING em {args.run} | {len(candles)} candles de {args.tf} "
              f"(~{span_h:.1f}h) | spread {args.spread_bps/100:.2f}% | ordem ${args.order:.0f}")
        print("=" * 64)
        print(f"Execuções     : {st['buys']} compras / {st['sells']} vendas "
              f"({st['round_trips']} idas-e-voltas)")
        print(f"Estoque no fim: {st['end_inventory_usdt']:+.2f} USDT")
        print(f"Taxas pagas   : -{st['fees']:.2f} USDT")
        marca = "✅ LUCRO" if st["net"] > 0 else "❌ prejuízo"
        print(f"LÍQUIDO       : {st['net']:+.2f} USDT ({summary_pct(st, args.max_inv):+.1f}% "
              f"do capital de ${args.max_inv:.0f})   {marca}")
        print("-" * 64)
        print("Lembre: a simulação assume execução quando o preço TOCA a ordem —")
        print("na vida real isso é otimista (fila/competição). É ordem de grandeza.")
        print("=" * 64)
        return 0

    from .demo import run_demo
    return run_demo()


def _run_grid(args) -> int:
    """Mede o grid em candles REAIS. Faixa automática pelo mínimo/máximo do período,
    a não ser que --lower/--upper sejam passados."""
    from .data import fetch_ohlcv
    candles = fetch_ohlcv(args.grid, args.tf, args.limit)
    if not candles:
        print("Sem candles — verifique o par/conexão.")
        return 1
    lows = [c[3] for c in candles]
    highs = [c[2] for c in candles]
    lower = args.lower if args.lower else min(lows)
    upper = args.upper if args.upper else max(highs)
    gp = GridParams(lower, upper, args.grids, args.leverage, args.capital)
    st = simulate_grid(candles, gp)
    span_h = len(candles) * (1 if args.tf.endswith("m") else 60) / 60.0
    print("=" * 66)
    print(f"GRID de futuros em {args.grid} | {len(candles)} candles de {args.tf} "
          f"(~{span_h:.1f}h)")
    print(f"Faixa: {lower:.4f} — {upper:.4f} | {args.grids} níveis | "
          f"alavancagem {args.leverage}x | margem ${args.capital:.0f}")
    print("=" * 66)
    print(f"Execuções     : {st['fills']} idas-e-voltas no grid")
    print(f"Estoque no fim: {st['end_inventory_usdt']:+.2f} USDT")
    print(f"Pior queda    : -{st['max_drawdown']*100:.1f}% (drawdown da margem)")
    if st["liquidated"]:
        marca = "💥 LIQUIDADO — a margem zerou (o preço rompeu a faixa e continuou)"
    else:
        marca = "✅ LUCRO" if st["net"] > 0 else "❌ prejuízo"
    print(f"LÍQUIDO       : {st['net']:+.2f} USDT ({st['return_pct']:+.1f}% "
          f"da margem de ${args.capital:.0f})   {marca}")
    print("-" * 66)
    print("Lembre: assume execução quando o preço TOCA o nível (otimista) e usa o")
    print("candle inteiro. É ordem de grandeza — pra escolher faixa e alavancagem")
    print("ANTES de ligar o grid nativo da Bybit com dinheiro real.")
    print("=" * 66)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
