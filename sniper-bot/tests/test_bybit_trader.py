"""Testes da matemática de ordem do agente Bybit (TP/SL e quantidade)."""

import pytest

from bybit_bot.trader import compute_qty, set_leverage_safe, tp_sl_prices


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


class _ExRaises:
    def __init__(self, msg):
        self.msg = msg
        self.called = False

    def set_leverage(self, leverage, symbol):
        self.called = True
        raise Exception(self.msg)


def test_set_leverage_ignora_110043():
    # 110043 = "leverage not modified" -> NÃO deve relançar (já está certo)
    ex = _ExRaises('bybit {"retCode":110043,"retMsg":"leverage not modified"}')
    set_leverage_safe(ex, 5, "NOM/USDT:USDT")   # não levanta
    assert ex.called


def test_set_leverage_relanca_outros_erros():
    ex = _ExRaises('bybit {"retCode":10001,"retMsg":"params error"}')
    with pytest.raises(Exception):
        set_leverage_safe(ex, 5, "NOM/USDT:USDT")


def test_pct_to_tp():
    from bybit_bot.panel import _pct_to_tp
    assert _pct_to_tp(100.0, 100.0, 106.0) == pytest.approx(0.0)     # na entrada
    assert _pct_to_tp(100.0, 103.0, 106.0) == pytest.approx(50.0)    # meio do caminho
    assert _pct_to_tp(100.0, 106.0, 106.0) == pytest.approx(100.0)   # no TP
    assert _pct_to_tp(100.0, 200.0, 106.0) == pytest.approx(100.0)   # não passa de 100
