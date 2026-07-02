"""Testes do filtro de mercado (macro) do agente Bybit."""

from bybit_bot.market import btc_change, compute_breadth, regime_ok


def _tk(pct):
    return {"percentage": pct}


def test_compute_breadth():
    tickers = {
        "AAA/USDT:USDT": _tk(5.0), "BBB/USDT:USDT": _tk(-2.0),
        "CCC/USDT:USDT": _tk(1.0), "DDD/USDT": _tk(9.0),   # não é perp -> ignora
    }
    # 3 perps, 2 positivos -> 0.666...
    assert abs(compute_breadth(tickers) - 2 / 3) < 1e-9


def test_compute_breadth_vazio():
    assert compute_breadth({}) == 0.0


def test_btc_change():
    assert btc_change({"BTC/USDT:USDT": _tk(2.5)}) == 0.025
    assert btc_change({}) == 0.0


def test_regime_ok():
    assert regime_ok(0.01, 0.50, -0.03, 0.35)        # tudo bem
    assert not regime_ok(-0.05, 0.50, -0.03, 0.35)   # BTC caindo forte
    assert not regime_ok(0.01, 0.20, -0.03, 0.35)    # poucos no positivo
