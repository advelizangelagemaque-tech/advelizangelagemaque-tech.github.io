"""Testes do backtester do Delta v2 (long/short em moedas líquidas)."""

from bybit_bot.delta_backtest import (metrics, path_return, rank_longs_shorts,
                                      simulate_delta)


def test_rank_longs_shorts():
    scores = {"A": 5, "B": 1, "C": 3, "D": -2}
    longs, shorts = rank_longs_shorts(scores, 1)
    assert longs == ["A"] and shorts == ["D"]      # mais forte / mais fraco


def test_path_return_long_e_short():
    assert abs(path_return([100, 110], 0, 1, +1, 0) - 0.10) < 1e-9   # long +10%
    assert abs(path_return([100, 110], 0, 1, -1, 0) + 0.10) < 1e-9   # short -10%


def test_path_return_stop_corta():
    # long que cai 30% (>25%) -> sai no stop de -25%
    assert path_return([100, 70], 0, 1, +1, 0.25) == -0.25
    # cai só 20% -> segura, retorno -20%
    assert abs(path_return([100, 80], 0, 1, +1, 0.25) + 0.20) < 1e-9


def _trending():
    # 3 moedas subindo firme, 3 caindo firme -> momentum deve lucrar
    days = 45
    up = [[100 * (1.01 ** d) for d in range(days)] for _ in range(3)]
    dn = [[100 * (0.99 ** d) for d in range(days)] for _ in range(3)]
    prices = {}
    for i, c in enumerate(up):
        prices[f"UP{i}"] = c
    for i, c in enumerate(dn):
        prices[f"DN{i}"] = c
    return prices


def test_momentum_lucra_em_tendencia():
    prices = _trending()
    mom = simulate_delta(prices, lookback=14, hold=7, k=3, stop=0.25, fee_bps=5, direction=1)
    rev = simulate_delta(prices, lookback=14, hold=7, k=3, stop=0.25, fee_bps=5, direction=-1)
    assert mom["final"] > 1.0            # momentum: long os que sobem, short os que caem
    assert rev["final"] < 1.0            # reversão faz o oposto -> perde


def test_metrics_calcula_drawdown_e_acertos():
    sim = {"final": 1.10, "curve": [1.0, 1.2, 1.0, 1.1], "periods": [0.2, -0.166, 0.1],
           "rebalances": 3}
    m = metrics(sim)
    assert abs(m["total_return"] - 0.10) < 1e-9
    assert m["max_drawdown"] > 0.15 and m["max_drawdown"] < 0.18   # caiu de 1.2 p/ 1.0
    assert abs(m["win_rate"] - 2 / 3) < 1e-9
