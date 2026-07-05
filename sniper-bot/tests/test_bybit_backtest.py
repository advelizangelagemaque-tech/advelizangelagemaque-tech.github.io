"""Testes do backtester (simulação da estratégia em candles históricos)."""

from bybit_bot.backtest import aggregate, simulate_symbol


def _p(**kw):
    # ema_len=1 e rsi 0..100 desligam esses filtros no teste — foco no dip + TP/SL.
    # bars_24h=0 desliga o filtro de 24h no teste (foco no dip + TP/SL).
    base = dict(dip_min=0.03, dip_max=0.10, tp_roi=0.30, sl_roi=0.15, leverage=5,
                rsi_period=14, rsi_min=0.0, rsi_max=100.0, ema_len=1, lookback=3,
                fee_roi=0.0, min_24h=-1.0, max_24h=99.0, bars_24h=0)
    base.update(kw)
    return base


def _c(o, h, l, c):
    return [0, o, h, l, c, 100]


# máxima recente 110, recua para 104 (dip ~5.5%) -> entra. TP=+6% (110.24), SL=-3% (100.88).
_BASE = [_c(100, 110, 100, 105), _c(105, 108, 104, 106),
         _c(106, 107, 105, 106), _c(106, 106, 105, 104)]   # i=3 = entrada


def test_simulate_hits_tp():
    candles = _BASE + [_c(104, 111, 104, 110)]     # bate TP (111 >= 110.24)
    trades = simulate_symbol(candles, _p())
    assert len(trades) == 1 and trades[0]["outcome"] == "TP"


def test_simulate_hits_sl():
    candles = _BASE + [_c(104, 104, 100, 100)]     # low 100 <= SL 100.88 -> SL
    trades = simulate_symbol(candles, _p())
    assert len(trades) == 1 and trades[0]["outcome"] == "SL"


def test_aggregate():
    trades = [{"roi": 0.30}, {"roi": -0.15}, {"roi": 0.30}, {"roi": -0.15}]
    st = aggregate(trades)
    assert st["count"] == 4 and st["wins"] == 2 and st["losses"] == 2
    assert st["win_rate"] == 0.5
    assert abs(st["total_roi"] - 0.30) < 1e-9          # 0.6 - 0.3
    assert st["profit_factor"] == 2.0                   # 0.6 / 0.3


def test_aggregate_vazio():
    st = aggregate([])
    assert st["count"] == 0 and st["expectancy"] == 0.0


def test_fee_desconta():
    candles = _BASE + [_c(104, 111, 104, 110)]
    trades = simulate_symbol(candles, _p(fee_roi=0.01))
    assert abs(trades[0]["roi"] - (0.30 - 0.01)) < 1e-9   # TP menos a taxa
