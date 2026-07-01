"""Testes da lógica do rastreador Bybit (dip em tendência de alta)."""

from types import SimpleNamespace

from bybit_bot.screener import compute_dip, find_candidates, is_entry, passes_trend


def _cfg(min_24h=0.20, max_24h=0.50, dip_min=0.03):
    return SimpleNamespace(min_24h=min_24h, max_24h=max_24h, dip_min=dip_min)


def test_passes_trend():
    assert passes_trend(0.30, 0.20, 0.50)
    assert not passes_trend(0.10, 0.20, 0.50)   # fraca
    assert not passes_trend(0.60, 0.20, 0.50)   # forte demais


def test_compute_dip():
    # topo 110, preço atual 104.5 -> recuo 5%
    assert compute_dip([100, 110, 108], 104.5) == 0.05
    assert compute_dip([], 100) == 0.0


def test_is_entry():
    cfg = _cfg()
    assert is_entry(0.30, 0.04, cfg)            # em alta + dip suficiente
    assert not is_entry(0.30, 0.01, cfg)        # dip pequeno
    assert not is_entry(0.10, 0.05, cfg)        # sem tendência


class _FakeEx:
    """Exchange ccxt falsa (sem rede)."""

    def __init__(self, tickers, ohlcv):
        self._tickers = tickers
        self._ohlcv = ohlcv

    def fetch_tickers(self):
        return self._tickers

    def fetch_ohlcv(self, symbol, timeframe, limit):
        return self._ohlcv.get(symbol, [])


def test_find_candidates():
    tickers = {
        "AAA/USDT:USDT": {"percentage": 30.0},   # alta ok
        "BBB/USDT:USDT": {"percentage": 5.0},     # fraca -> fora
        "CCC/USDT:USDT": {"percentage": 35.0},    # alta ok, mas sem dip
        "DDD/USDT": {"percentage": 40.0},         # não é perp :USDT -> fora
    }
    ohlcv = {
        # [ts, open, high, low, close] — AAA recuou de 110 p/ 104.5 (5%)
        "AAA/USDT:USDT": [[0, 100, 110, 99, 104.5]],
        "CCC/USDT:USDT": [[0, 100, 105, 99, 105]],   # sem dip (está na máxima)
    }
    cands = find_candidates(_FakeEx(tickers, ohlcv), _cfg())
    assert [c["symbol"] for c in cands] == ["AAA/USDT:USDT"]
    assert abs(cands[0]["dip"] - 0.05) < 1e-9
