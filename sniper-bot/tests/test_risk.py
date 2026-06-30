"""Testes de cálculo de quantidade, arredondamento e TP/SL."""

import pytest

from sniper.risk import (compute_quantity, round_step, round_tick, tp_sl_prices,
                         validate_order)


def test_round_step_arredonda_para_baixo():
    assert round_step(30.0049, 0.001) == pytest.approx(30.004)
    assert round_step(5.0, 0) == 5.0  # step 0 = sem arredondamento


def test_round_tick():
    assert round_tick(2.013, 0.01) == pytest.approx(2.01)
    assert round_tick(2.017, 0.01) == pytest.approx(2.02)


def test_compute_quantity(sym):
    # margem 20 * lev 3 = 60 notional; /2.0 = 30
    assert compute_quantity(2.0, 20, 3, sym) == pytest.approx(30.0)


def test_compute_quantity_preco_invalido(sym):
    with pytest.raises(ValueError):
        compute_quantity(0, 20, 3, sym)


def test_validate_order_rejeita_qty_zero(sym):
    with pytest.raises(ValueError):
        validate_order(0, 2.0, sym)


def test_validate_order_rejeita_abaixo_do_min_notional(sym):
    # qty 1 * preço 2 = 2 < min_notional 5
    with pytest.raises(ValueError):
        validate_order(1, 2.0, sym)


def test_tp_sl_long(sym):
    tp, sl = tp_sl_prices(2.0, "BUY", 0.10, 0.05, sym)
    assert tp == pytest.approx(2.20)
    assert sl == pytest.approx(1.90)


def test_tp_sl_short(sym):
    tp, sl = tp_sl_prices(2.0, "SELL", 0.10, 0.05, sym)
    assert tp == pytest.approx(1.80)
    assert sl == pytest.approx(2.10)
