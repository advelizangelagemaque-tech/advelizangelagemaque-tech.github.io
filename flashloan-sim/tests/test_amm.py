"""Testes da matemática da DEX (Uniswap V2)."""

from flashsim.amm import amount_out, price_impact, spot_price


def test_amount_out_sem_taxa():
    # pool 1000/1000, sem taxa: trocar 100 rende <100 por causa do slippage
    out = amount_out(100, 1000, 1000, fee_bps=0)
    # fórmula: 100*1000/(1000+100) = 90.909...
    assert abs(out - 90.9090909) < 1e-4


def test_amount_out_com_taxa_rende_menos():
    sem = amount_out(100, 1000, 1000, fee_bps=0)
    com = amount_out(100, 1000, 1000, fee_bps=30)   # 0.30%
    assert com < sem


def test_amount_out_invalido():
    assert amount_out(0, 1000, 1000, 30) == 0.0
    assert amount_out(100, 0, 1000, 30) == 0.0
    assert amount_out(-5, 1000, 1000, 30) == 0.0


def test_spot_price():
    assert spot_price(1000, 2000) == 2.0     # 1 in vale 2 out
    assert spot_price(0, 100) == 0.0


def test_price_impact_cresce_com_tamanho():
    pequeno = price_impact(1, 1_000_000, 1_000_000, 30)
    grande = price_impact(100_000, 1_000_000, 1_000_000, 30)
    assert grande > pequeno >= 0
