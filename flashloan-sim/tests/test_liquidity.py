"""Testes do filtro de liquidez — a correção que mata as 'bordas' de milhões %."""

from flashsim.scan import _filter_liquid, _price_map


def _pool(dex, a, b, ra, rb, fee=30):
    return {"dex": dex, "a": a, "b": b, "res_a": ra, "res_b": rb, "fee": fee}


def test_price_map_ancorado_no_stable():
    # pool WETH/USDC.e com 10 WETH e 30000 USDC.e -> WETH ~ $3000
    pools = {frozenset(("WETH", "USDC.e")): [_pool("Q", "WETH", "USDC.e", 10, 30000)]}
    prices = _price_map(pools)
    assert prices["USDC.e"] == 1.0
    assert abs(prices["WETH"] - 3000) < 1e-6


def test_price_map_propaga_dois_saltos():
    # USDC.e->WETH e WETH->WBTC: dá pra estimar o preço do WBTC via WETH
    pools = {
        frozenset(("WETH", "USDC.e")): [_pool("Q", "WETH", "USDC.e", 10, 30000)],  # WETH=$3000
        frozenset(("WBTC", "WETH")): [_pool("Q", "WBTC", "WETH", 1, 20)],           # 1 WBTC=20 WETH
    }
    prices = _price_map(pools)
    assert abs(prices["WBTC"] - 60000) < 1e-3       # 20 * 3000


def test_filtro_descarta_poeira():
    # uma pool boa (liquidez ~\$30k) e uma de poeira (\$3) -> só a boa fica
    pools = {
        frozenset(("WETH", "USDC.e")): [_pool("Q", "WETH", "USDC.e", 10, 30000)],
        frozenset(("CRV", "USDC.e")): [_pool("Q", "CRV", "USDC.e", 3, 3)],   # ~\$3: poeira
    }
    prices = _price_map(pools)
    out, dropped = _filter_liquid(pools, prices, min_usd=20000)
    assert frozenset(("WETH", "USDC.e")) in out
    assert frozenset(("CRV", "USDC.e")) not in out
    assert dropped == 1


def test_filtro_descarta_token_sem_preco():
    # token que não conecta a nenhum stable -> sem preço -> descartado (conservador)
    pools = {frozenset(("XYZ", "ABC")): [_pool("Q", "XYZ", "ABC", 1000, 1000)]}
    prices = _price_map(pools)
    out, dropped = _filter_liquid(pools, prices, min_usd=1)
    assert out == {} and dropped == 1
