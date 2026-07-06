"""Fumaça: a demonstração roda inteira sem erro e chega às conclusões certas."""

from flashsim.chains import CHAINS, get_chain
from flashsim.demo import run_demo
from flashsim.simulate import Pool, find_arbitrage


def test_demo_roda():
    assert run_demo() == 0


def test_lista_de_redes_baratas():
    # as redes baratas devem ter gás bem menor que a Ethereum
    assert CHAINS["polygon"].gas_usd < CHAINS["ethereum"].gas_usd
    assert get_chain("BASE").key == "base"


def test_conclusao_gap_grande_rede_barata_da_lucro():
    p1 = Pool("A", 500_000, 500_000, 30)
    p2 = Pool("B", 500_000, 485_000, 30)      # ~3%
    op = find_arbitrage("X/USDC", p1, p2, flash_fee_bps=5, gas_usd=0.03)
    assert op.net_profit > 0                   # rede barata: sobra lucro


def test_conclusao_mesmo_gap_ethereum_da_prejuizo():
    p1 = Pool("A", 1_000_000, 1_000_000, 30)
    p2 = Pool("B", 1_000_000, 995_000, 30)     # ~0.5%
    op = find_arbitrage("X/USDC", p1, p2, flash_fee_bps=5, gas_usd=25.0)
    assert op.net_profit < 0                   # gás da Ethereum come o gap
