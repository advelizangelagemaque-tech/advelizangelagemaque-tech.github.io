"""Simulação de MARKET MAKING sobre candles. Pura e testável.

A cada candle a gente 'coloca' uma ordem de compra logo abaixo do preço e uma de
venda logo acima (spread). Se o preço tocou a compra -> compramos; se tocou a
venda -> vendemos. Ganhamos o spread no vai-e-vem; mas se o preço anda forte pra
um lado só, acumulamos ESTOQUE do lado errado (o risco do market making). No fim,
o estoque é marcado a mercado — e é aí que o prejuízo de estoque aparece.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MMParams:
    spread_bps: float = 10.0      # spread total (compra->venda) em pontos-base (10 = 0.10%)
    order_size: float = 20.0      # tamanho de cada ordem, em USDT (notional)
    max_inventory: float = 100.0  # teto de estoque por lado, em USDT (controla o risco)
    maker_fee_bps: float = 2.0    # taxa de maker por execução (Bybit perp ~0.02%)


def simulate_mm(candles: list, p: MMParams) -> dict:
    """Roda o market making nos candles [ts,open,high,low,close,vol]. Devolve o resumo.

    Aproximação honesta: assume que a ordem executa quando o preço TOCA o nosso
    preço — na vida real isso superestima as execuções (fila, competição). Serve
    para medir a ORDEM DE GRANDEZA e ver spread vs estoque.
    """
    cash = 0.0
    inv = 0.0                     # estoque em unidades do ativo (pode ser +/-)
    buys = sells = 0
    fees = 0.0
    half = (p.spread_bps / 2) / 10_000.0
    fee = p.maker_fee_bps / 10_000.0
    for c in candles:
        o, h, l = c[1], c[2], c[3]
        if o <= 0:
            continue
        bid = o * (1 - half)
        ask = o * (1 + half)
        if l <= bid and inv * o < p.max_inventory:          # tocou a compra
            sz = p.order_size / bid
            cost = bid * sz
            f = cost * fee
            cash -= cost + f
            inv += sz
            fees += f
            buys += 1
        if h >= ask and inv * o > -p.max_inventory:         # tocou a venda
            sz = p.order_size / ask
            proceeds = ask * sz
            f = proceeds * fee
            cash += proceeds - f
            inv -= sz
            fees += f
            sells += 1
    last = candles[-1][4] if candles else 0.0
    inv_val = inv * last
    net = cash + inv_val                                    # P&L total (spread + estoque - taxas)
    return {
        "net": net, "buys": buys, "sells": sells, "round_trips": min(buys, sells),
        "fees": fees, "end_inventory_usdt": inv_val,
        "spread_gross": (buys + sells) * (p.spread_bps / 2 / 10_000.0) * p.order_size,
    }


def summary_pct(stats: dict, capital: float) -> float:
    """Lucro líquido como % do capital exposto (o max_inventory)."""
    return stats["net"] / capital * 100 if capital > 0 else 0.0
