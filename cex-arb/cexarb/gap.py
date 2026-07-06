"""Matemática da arbitragem entre corretoras (CEX-CEX). Pura e testável.

O ponto central: o gap 'de vitrine' (diferença dos preços do meio) engana. O que
importa é o spread EXECUTÁVEL: você compra no ask (mais caro) de uma e vende no bid
(mais barato) da outra, e ainda paga taxa dos dois lados. Aqui a gente calcula
exatamente isso.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Book:
    """Topo do livro de ordens de UMA corretora para um par."""
    exchange: str
    bid: float     # melhor compra (o maior preço que alguém paga agora)
    ask: float     # melhor venda (o menor preço que alguém vende agora)


@dataclass
class GapResult:
    symbol: str
    buy_ex: str            # onde comprar (barato)
    sell_ex: str           # onde vender (caro)
    displayed_gap_pct: float   # diferença 'de vitrine' (preços do meio)
    net_pct: float             # spread REAL depois de cruzar o livro e as taxas
    net_usd_per_1k: float      # lucro líquido por 1.000 USDT movimentados
    profitable: bool


def _mid(b: Book) -> float:
    return (b.bid + b.ask) / 2.0


def net_arb(a: Book, b: Book, fee_a: float, fee_b: float) -> tuple[str, str, float]:
    """Melhor direção e o spread líquido (fração) já com as taxas dos dois lados.

    fee_a/fee_b = taxa de taker de cada corretora em fração (0.1% = 0.001).
    """
    # direção 1: compra em A (paga ask), vende em B (recebe bid)
    cost1 = a.ask * (1 + fee_a)
    recv1 = b.bid * (1 - fee_b)
    pct1 = (recv1 - cost1) / cost1 if cost1 > 0 else -1.0
    # direção 2: compra em B, vende em A
    cost2 = b.ask * (1 + fee_b)
    recv2 = a.bid * (1 - fee_a)
    pct2 = (recv2 - cost2) / cost2 if cost2 > 0 else -1.0
    if pct1 >= pct2:
        return a.exchange, b.exchange, pct1
    return b.exchange, a.exchange, pct2


def compute_gap(symbol: str, a: Book, b: Book, fee_a: float, fee_b: float) -> GapResult:
    """Compara as duas corretoras e devolve o gap de vitrine vs o lucro real."""
    ma, mb = _mid(a), _mid(b)
    displayed = abs(ma - mb) / min(ma, mb) if min(ma, mb) > 0 else 0.0
    buy_ex, sell_ex, net = net_arb(a, b, fee_a, fee_b)
    return GapResult(
        symbol=symbol, buy_ex=buy_ex, sell_ex=sell_ex,
        displayed_gap_pct=displayed * 100, net_pct=net * 100,
        net_usd_per_1k=net * 1000, profitable=net > 0,
    )
