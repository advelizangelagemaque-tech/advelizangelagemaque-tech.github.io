"""Simula uma arbitragem entre DUAS pools da MESMA dupla (ex: TOKEN/USDC).

Ideia: pegar USDC emprestado (flash loan), comprar o TOKEN onde está barato,
vender onde está caro, devolver o empréstimo — tudo na mesma transação. Aqui a
gente calcula o lucro LÍQUIDO de verdade: ganho bruto menos taxa das DEXs (já
embutida no swap) menos taxa do flash loan menos o gás. Puro e testável.
"""

from __future__ import annotations

from dataclasses import dataclass

from .amm import amount_out, spot_price


@dataclass
class Pool:
    """Uma pool de DEX para a dupla TOKEN/USDC (reservas em unidades humanas)."""
    dex: str
    usdc: float          # reserva de USDC (a 'perna' emprestada)
    token: float         # reserva do TOKEN
    fee_bps: float = 30  # taxa da DEX (Uniswap V2 = 30 = 0.30%)


@dataclass
class Opportunity:
    pair: str
    buy_dex: str          # onde compramos o token (barato)
    sell_dex: str         # onde vendemos o token (caro)
    borrow_usdc: float    # quanto pegar emprestado (ótimo)
    gross_profit: float   # ganho antes dos custos de flash+gás
    flash_fee: float      # custo do empréstimo
    gas_usd: float        # custo do gás estimado
    net_profit: float     # >0 = valeria a pena
    spread_pct: float     # diferença de preço 'de vitrine' entre as duas DEXs


def _one_way(borrow: float, buy: Pool, sell: Pool, flash_fee_bps: float) -> float:
    """Lucro (só flash fee, sem gás) de: emprestar `borrow` USDC, comprar token na
    pool `buy`, vender na pool `sell`, devolver o empréstimo."""
    tok = amount_out(borrow, buy.usdc, buy.token, buy.fee_bps)      # USDC -> TOKEN
    usdc_back = amount_out(tok, sell.token, sell.usdc, sell.fee_bps)  # TOKEN -> USDC
    flash_fee = borrow * flash_fee_bps / 10_000.0
    return usdc_back - borrow - flash_fee


def _maximize(buy: Pool, sell: Pool, flash_fee_bps: float) -> tuple[float, float]:
    """Acha o empréstimo que dá o maior lucro (busca por seção áurea).
    O lucro sobe e depois cai com o tamanho (slippage), então tem um pico."""
    lo, hi = 0.0, 0.5 * min(buy.usdc, sell.usdc)   # não faz sentido passar da metade da pool
    if hi <= 0:
        return 0.0, 0.0
    gr = (5 ** 0.5 - 1) / 2                         # ~0.618
    a, b = lo, hi
    c = b - gr * (b - a)
    d = a + gr * (b - a)
    fc = _one_way(c, buy, sell, flash_fee_bps)
    fd = _one_way(d, buy, sell, flash_fee_bps)
    for _ in range(80):                            # converge bem em ~80 passos
        if fc < fd:
            a, c, fc = c, d, fd
            d = a + gr * (b - a)
            fd = _one_way(d, buy, sell, flash_fee_bps)
        else:
            b, d, fd = d, c, fc
            c = b - gr * (b - a)
            fc = _one_way(c, buy, sell, flash_fee_bps)
    best_x = (a + b) / 2
    return best_x, _one_way(best_x, buy, sell, flash_fee_bps)


def find_arbitrage(pair: str, p1: Pool, p2: Pool, *, flash_fee_bps: float = 5,
                   gas_usd: float = 0.05) -> Opportunity:
    """Melhor arbitragem entre p1 e p2 para a dupla `pair`.

    flash_fee_bps: taxa do flash loan (Aave v3 = ~5 = 0.05%; alguns = 0).
    gas_usd: custo estimado do gás da transação, em dólar (varia por rede).
    Testa as duas direções (comprar em p1 ou em p2) e escolhe a melhor.
    """
    # direção A: compra em p1, vende em p2 ; direção B: o contrário
    xa, ga = _maximize(p1, p2, flash_fee_bps)
    xb, gb = _maximize(p2, p1, flash_fee_bps)
    if ga >= gb:
        buy, sell, borrow, gross = p1, p2, xa, ga
    else:
        buy, sell, borrow, gross = p2, p1, xb, gb

    flash_fee = borrow * flash_fee_bps / 10_000.0
    net = gross - gas_usd
    # spread 'de vitrine': quão diferente é o preço do token entre as duas DEXs
    pr1 = spot_price(p1.token, p1.usdc)   # preço do TOKEN em USDC na p1
    pr2 = spot_price(p2.token, p2.usdc)
    spread = abs(pr1 - pr2) / min(pr1, pr2) if min(pr1, pr2) > 0 else 0.0

    return Opportunity(
        pair=pair, buy_dex=buy.dex, sell_dex=sell.dex,
        borrow_usdc=max(0.0, borrow), gross_profit=gross, flash_fee=flash_fee,
        gas_usd=gas_usd, net_profit=net, spread_pct=spread * 100,
    )
