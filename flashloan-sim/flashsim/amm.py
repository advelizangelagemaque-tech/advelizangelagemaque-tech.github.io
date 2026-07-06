"""Matemática de uma DEX estilo Uniswap V2 (produto constante x*y=k).

É a base de tudo: o preço numa DEX não é fixo — quanto mais você compra, mais o
preço sobe (slippage). Estas funções calculam exatamente quanto você RECEBE ao
trocar, já com a taxa da DEX embutida. São puras (sem rede) e testáveis.
"""

from __future__ import annotations


def amount_out(amount_in: float, reserve_in: float, reserve_out: float,
               fee_bps: float) -> float:
    """Quanto sai ao trocar `amount_in` numa pool com essas reservas.

    fee_bps = taxa da DEX em pontos-base (0.30% = 30). Fórmula do Uniswap V2:
    aplica a taxa na entrada e usa o produto constante para o resto.
    """
    if amount_in <= 0 or reserve_in <= 0 or reserve_out <= 0:
        return 0.0
    fee_mult = (10_000.0 - fee_bps) / 10_000.0
    in_after_fee = amount_in * fee_mult
    return in_after_fee * reserve_out / (reserve_in + in_after_fee)


def spot_price(reserve_in: float, reserve_out: float) -> float:
    """Preço 'de vitrine' (1 unidade de in vale quanto de out), sem taxa/slippage."""
    if reserve_in <= 0:
        return 0.0
    return reserve_out / reserve_in


def price_impact(amount_in: float, reserve_in: float, reserve_out: float,
                 fee_bps: float) -> float:
    """Fração de quanto o preço piorou por causa do tamanho da ordem (slippage)."""
    if amount_in <= 0 or reserve_in <= 0 or reserve_out <= 0:
        return 0.0
    ideal = amount_in * spot_price(reserve_in, reserve_out)
    real = amount_out(amount_in, reserve_in, reserve_out, fee_bps)
    if ideal <= 0:
        return 0.0
    return max(0.0, (ideal - real) / ideal)
