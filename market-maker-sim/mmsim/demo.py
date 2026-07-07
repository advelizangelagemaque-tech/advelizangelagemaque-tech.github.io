"""Demonstração: mostra a lição central do market making em dois mercados.

- Mercado DE LADO (oscila numa faixa): o MM colhe o spread -> lucro.
- Mercado EM TENDÊNCIA (só sobe): o MM acumula estoque do lado errado -> prejuízo.

Tudo sintético e determinístico (sem internet), só para VER o conceito.
"""

from __future__ import annotations

import math

from .mm import MMParams, simulate_mm, summary_pct


def _candles_ranging(n: int = 300, base: float = 100.0, amp: float = 0.03) -> list:
    """Preço oscilando numa faixa (sobe e desce em torno da base)."""
    out = []
    prev = base
    for i in range(n):
        mid = base * (1 + amp * math.sin(i / 4.0))
        o, c = prev, mid
        hi = max(o, c) * 1.002
        lo = min(o, c) * 0.998
        out.append([i, o, hi, lo, c, 1000])
        prev = mid
    return out


def _candles_trending(n: int = 300, base: float = 100.0, drift: float = 0.0015) -> list:
    """Preço subindo firme (tendência forte de alta). Candles 'limpos' de alta:
    sem pavio pra baixo — o preço só sobe, então SÓ a ordem de venda executa e a
    gente vai ficando com estoque VENDIDO (short) num ativo que sobe = prejuízo."""
    out = []
    prev = base
    for i in range(n):
        mid = base * (1 + drift * i)
        o, c = prev, mid
        hi = max(o, c)            # topo = fechamento (sem exagero pra cima)
        lo = min(o, c)            # fundo = abertura (sem pavio pra baixo -> compra não executa)
        out.append([i, o, hi, lo, c, 1000])
        prev = mid
    return out


def _fmt(title: str, stats: dict, capital: float) -> str:
    ok = "✅ LUCRO" if stats["net"] > 0 else "❌ prejuízo"
    return (
        f"• {title}\n"
        f"    Execuções: {stats['buys']} compras / {stats['sells']} vendas "
        f"({stats['round_trips']} idas-e-voltas)\n"
        f"    Estoque no fim: {stats['end_inventory_usdt']:+.2f} USDT | "
        f"taxas: -{stats['fees']:.2f}\n"
        f"    >>> Líquido: {stats['net']:+.2f} USDT "
        f"({summary_pct(stats, capital):+.1f}% do capital)   {ok}\n"
    )


def run_demo() -> int:
    p = MMParams(spread_bps=10, order_size=20, max_inventory=100, maker_fee_bps=2)
    print("=" * 64)
    print("DEMONSTRAÇÃO — market making (só simulação, ZERO risco)")
    print("=" * 64)
    print(f"Config: spread 0.10% | ordem $20 | teto de estoque $100 | taxa 0.02%\n")

    print(_fmt("Mercado DE LADO (oscila) — o cenário bom pro MM",
               simulate_mm(_candles_ranging(), p), p.max_inventory))
    print(_fmt("Mercado EM TENDÊNCIA (só sobe) — o cenário ruim",
               simulate_mm(_candles_trending(), p), p.max_inventory))

    print("=" * 64)
    print("LIÇÃO: o market making é uma máquina de colher SPREAD — ótima quando o")
    print("preço oscila de lado, e perigosa quando ele dispara pra um lado só (o")
    print("estoque vira um saco do lado errado). O segredo é operar em faixas e")
    print("controlar o estoque. O modo --run mede isso com preços REAIS.")
    print("=" * 64)
    return 0
