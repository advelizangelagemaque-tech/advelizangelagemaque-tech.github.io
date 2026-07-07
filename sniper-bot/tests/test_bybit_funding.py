"""Testes da colheita de funding do Delta (escolhe os lados para RECEBER)."""

from bybit_bot.delta import eligible_rows, rank_basket


def _t(pct, funding, vol=9e6):
    return {"percentage": pct, "quoteVolume": vol, "info": {"fundingRate": str(funding)}}


TICKERS = {
    "A/USDT:USDT": _t(1, 0.0010),    # funding +0.10% (mais alto)
    "B/USDT:USDT": _t(2, 0.0005),
    "C/USDT:USDT": _t(3, -0.0002),
    "D/USDT:USDT": _t(4, -0.0008),   # funding -0.08% (mais negativo)
}


def test_funding_vira_score_negado():
    rows = eligible_rows(TICKERS, 5e6, by_funding=True)
    by = {r["symbol"]: r for r in rows}
    assert abs(by["A/USDT:USDT"]["score"] - (-0.0010)) < 1e-9   # score = -funding
    assert by["A/USDT:USDT"]["funding"] == 0.0010


def test_shorta_funding_alto_longa_funding_baixo():
    rows = eligible_rows(TICKERS, 5e6, by_funding=True)
    longs, shorts = rank_basket(rows, 1)
    # LONG = funding mais NEGATIVO (recebe quando funding<0) -> D
    assert longs == ["D/USDT:USDT"]
    # SHORT = funding mais POSITIVO (recebe quando funding>0) -> A
    assert shorts == ["A/USDT:USDT"]


def test_sem_funding_no_ticker_e_ignorado():
    tk = {"X/USDT:USDT": {"quoteVolume": 9e6, "info": {}},        # sem fundingRate
          "Y/USDT:USDT": _t(1, 0.0003)}
    rows = eligible_rows(tk, 5e6, by_funding=True)
    assert {r["symbol"] for r in rows} == {"Y/USDT:USDT"}


def test_modo_momentum_continua_igual():
    rows = eligible_rows(TICKERS, 5e6, by_funding=False)
    by = {r["symbol"]: r for r in rows}
    assert by["D/USDT:USDT"]["score"] == 0.04        # volta a ser a alta 24h
    longs, shorts = rank_basket(rows, 1)
    assert longs == ["D/USDT:USDT"] and shorts == ["A/USDT:USDT"]  # por momentum
