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


def cycle_edge(legs: list[Leg], flash_fee_bps: float = 0.0) -> float:
    """A 'borda' do ciclo para um valor infinitesimal: produto das taxas de câmbio
    (já com a taxa de cada DEX) menos 1. É o detector puro de fresta:

      > 0  -> existe fresta (o loop rende, ao menos em tamanho pequeno);
      < 0  -> não há fresta, e o número diz QUÃO LONGE do break-even a gente está.

    Ignora o gás (que é custo fixo) — serve para achar ONDE a fresta quase abre.
    """
    rate = 1.0
    for leg in legs:
        if leg.reserve_in <= 0 or leg.reserve_out <= 0:
            return -1.0
        rate *= (leg.reserve_out / leg.reserve_in) * (1 - leg.fee_bps / 10_000.0)
    rate *= (1 - flash_fee_bps / 10_000.0)          # taxa do flash loan sobre a base
    return rate - 1.0


def _profit(x: float, legs: list[Leg], flash_fee_bps: float = 0.0) -> float:
    """Lucro bruto (antes do gás): quanto volta menos o que entrou e a taxa do flash."""
    return simulate_cycle(x, legs) - x - x * flash_fee_bps / 10_000.0


def optimize_cycle(legs: list[Leg], flash_fee_bps: float = 0.0) -> tuple[float, float]:
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
    fc, fd = _profit(c, legs, flash_fee_bps), _profit(d, legs, flash_fee_bps)
    for _ in range(80):
        if fc < fd:
            a, c, fc = c, d, fd
            d = a + gr * (b - a)
            fd = _profit(d, legs, flash_fee_bps)
        else:
            b, d, fd = d, c, fc
            c = b - gr * (b - a)
            fc = _profit(c, legs, flash_fee_bps)
    x = (a + b) / 2
    p = _profit(x, legs, flash_fee_bps)
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
    edge: float              # borda marginal (fresta se > 0)


def evaluate_cycle(legs: list[Leg], gas_usd: float,
                   flash_fee_bps: float = 0.0) -> CycleOpportunity:
    """Avalia um ciclo completo e devolve o resultado líquido (com gás e flash)."""
    x, gross = optimize_cycle(legs, flash_fee_bps)
    path = [legs[0].token_in] + [leg.token_out for leg in legs]
    return CycleOpportunity(
        path=path, dexes=[leg.dex for leg in legs], borrow=x,
        gross_profit=gross, gas_usd=gas_usd, net_profit=gross - gas_usd,
        edge=cycle_edge(legs, flash_fee_bps),
    )
