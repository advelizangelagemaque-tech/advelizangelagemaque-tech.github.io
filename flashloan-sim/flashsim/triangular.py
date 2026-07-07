"""Arbitragem TRIANGULAR (e em ciclo): base → A → B → base.

A fresta que a arbitragem de 2 pontas não acha costuma estar no LOOP: mesmo quando
cada par parece 'colado', a volta inteira pode render mais do que entrou. Aqui a
gente encadeia os swaps (cada perna com sua taxa) e acha o tamanho ótimo. Puro e
testável — sem rede.
"""

from __future__ import annotations

from dataclasses import dataclass

from .amm import amount_out


@dataclass
class Leg:
    """Uma perna do ciclo: trocar o token de entrada pelo de saída nesta pool."""
    dex: str
    token_in: str
    token_out: str
    reserve_in: float
    reserve_out: float
    fee_bps: float = 30


def simulate_cycle(amount_in: float, legs: list[Leg]) -> float:
    """Quanto volta ao passar `amount_in` por todas as pernas em sequência."""
    amt = amount_in
    for leg in legs:
        amt = amount_out(amt, leg.reserve_in, leg.reserve_out, leg.fee_bps)
        if amt <= 0:
            return 0.0
    return amt


def _profit(x: float, legs: list[Leg]) -> float:
    """Lucro bruto (antes do gás): quanto volta menos quanto entrou."""
    return simulate_cycle(x, legs) - x


def optimize_cycle(legs: list[Leg]) -> tuple[float, float]:
    """Acha o valor de entrada que dá o maior lucro bruto no ciclo (seção áurea).
    Devolve (entrada_ótima, lucro_bruto). Se nunca dá lucro, entrada ~0."""
    if not legs:
        return 0.0, 0.0
    hi = 0.5 * min(leg.reserve_in for leg in legs)   # não passa da metade da menor pool
    if hi <= 0:
        return 0.0, 0.0
    gr = (5 ** 0.5 - 1) / 2
    a, b = 0.0, hi
    c = b - gr * (b - a)
    d = a + gr * (b - a)
    fc, fd = _profit(c, legs), _profit(d, legs)
    for _ in range(80):
        if fc < fd:
            a, c, fc = c, d, fd
            d = a + gr * (b - a)
            fd = _profit(d, legs)
        else:
            b, d, fd = d, c, fc
            c = b - gr * (b - a)
            fc = _profit(c, legs)
    x = (a + b) / 2
    p = _profit(x, legs)
    if p <= 0:                     # nenhuma fresta: melhor não entrar
        return 0.0, 0.0
    return x, p


@dataclass
class CycleOpportunity:
    path: list[str]          # ex: ["USDC", "WETH", "WMATIC", "USDC"]
    dexes: list[str]         # a DEX usada em cada perna
    borrow: float            # entrada ótima (na moeda base)
    gross_profit: float
    gas_usd: float
    net_profit: float


def evaluate_cycle(legs: list[Leg], gas_usd: float) -> CycleOpportunity:
    """Avalia um ciclo completo e devolve o resultado líquido (com gás)."""
    x, gross = optimize_cycle(legs)
    path = [legs[0].token_in] + [leg.token_out for leg in legs]
    return CycleOpportunity(
        path=path, dexes=[leg.dex for leg in legs], borrow=x,
        gross_profit=gross, gas_usd=gas_usd, net_profit=gross - gas_usd,
    )
