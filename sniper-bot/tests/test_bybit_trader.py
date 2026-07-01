"""Testes da matemática de ordem do agente Bybit (TP/SL e quantidade)."""

import pytest

from bybit_bot.trader import compute_qty, tp_sl_prices


def test_tp_sl_prices_5x():
    # entry 100, TP +30% ROI, SL -15% ROI, 5x -> preço +6% / -3%
    tp, sl = tp_sl_prices(100.0, 0.30, 0.15, 5)
    assert tp == pytest.approx(106.0)
    assert sl == pytest.approx(97.0)


def test_tp_maior_que_sl():
    tp, sl = tp_sl_prices(100.0, 0.30, 0.15, 5)
    assert (tp - 100) > (100 - sl)   # alvo maior que o risco (em preço)


def test_compute_qty():
    # margem 10, 5x -> notional 50; preço 0.05 -> 1000 contratos
    assert compute_qty(10.0, 5, 0.05) == pytest.approx(1000.0)


def test_compute_qty_preco_invalido():
    with pytest.raises(ValueError):
        compute_qty(10.0, 5, 0)
