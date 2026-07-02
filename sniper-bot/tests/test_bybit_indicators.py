"""Testes dos indicadores técnicos (RSI, EMA) e do filtro de entrada."""

from bybit_bot.indicators import ema, rsi, ta_ok


def test_rsi_sem_dados():
    assert rsi([1, 2, 3], period=14) is None


def test_rsi_tudo_subindo():
    # sequência sempre subindo -> RSI = 100
    closes = list(range(1, 30))
    assert rsi(closes, period=14) == 100.0


def test_rsi_tudo_caindo():
    closes = list(range(30, 1, -1))
    assert rsi(closes, period=14) == 0.0


def test_rsi_intermediario():
    # alterna +2/-1 -> mais ganho que perda -> RSI > 50
    closes = [100.0]
    for i in range(20):
        closes.append(closes[-1] + (2 if i % 2 == 0 else -1))
    r = rsi(closes, period=14)
    assert 50 < r < 100


def test_ema_constante():
    assert ema([5, 5, 5, 5], 3) == 5.0


def test_ema_vazio():
    assert ema([], 10) is None


def test_ta_ok():
    # RSI saudável (55), preço acima da EMA -> ok
    assert ta_ok(55.0, 110.0, 100.0, 40.0, 72.0)
    # RSI esticado (80) -> bloqueia
    assert not ta_ok(80.0, 110.0, 100.0, 40.0, 72.0)
    # RSI em queda (30) -> bloqueia
    assert not ta_ok(30.0, 110.0, 100.0, 40.0, 72.0)
    # preço abaixo da média -> bloqueia
    assert not ta_ok(55.0, 90.0, 100.0, 40.0, 72.0)
    # sem dados (None) -> não bloqueia
    assert ta_ok(None, 90.0, None, 40.0, 72.0)
