"""Testes da estratégia Delta (long/short neutro)."""

from bybit_bot.delta import (
    eligible_rows,
    per_position_notional,
    rank_basket,
    rebalance_actions,
)


def test_eligible_rows_filtra_volume_e_perp():
    tickers = {
        "AAA/USDT:USDT": {"percentage": 30.0, "quoteVolume": 9_000_000},
        "BBB/USDT:USDT": {"percentage": -5.0, "quoteVolume": 1_000_000},   # ilíquido -> fora
        "CCC/USDT": {"percentage": 10.0, "quoteVolume": 9_000_000},         # não é perp -> fora
        "DDD/USDT:USDT": {"percentage": None, "quoteVolume": 9_000_000},    # sem % -> fora
    }
    rows = eligible_rows(tickers, min_vol_usdt=5_000_000)
    assert [r["symbol"] for r in rows] == ["AAA/USDT:USDT"]


def test_rank_basket():
    rows = [
        {"symbol": "A", "score": 0.50}, {"symbol": "B", "score": 0.30},
        {"symbol": "C", "score": 0.10}, {"symbol": "D", "score": -0.10},
        {"symbol": "E", "score": -0.30}, {"symbol": "F", "score": -0.50},
    ]
    longs, shorts = rank_basket(rows, k=2)
    assert longs == ["A", "B"]          # mais fortes
    assert shorts == ["F", "E"] or shorts == ["E", "F"]  # mais fracos (ordem do slice)
    assert set(longs).isdisjoint(shorts)


def test_rank_basket_poucos_ativos():
    rows = [{"symbol": "A", "score": 0.2}, {"symbol": "B", "score": -0.2}]
    longs, shorts = rank_basket(rows, k=5)   # pede 5, só tem 2 -> encolhe p/ 1 cada
    assert longs == ["A"] and shorts == ["B"]


def test_per_position_notional():
    assert per_position_notional(120.0, 1.0, 10) == 12.0
    assert per_position_notional(120.0, 1.0, 0) == 0.0


def test_rebalance_actions():
    current = {"A": "long", "X": "short", "Z": "long"}   # Z sai; X vira long
    longs, shorts = ["A", "X"], ["W"]
    acts = rebalance_actions(current, longs, shorts)
    # Z não está no alvo -> fecha; X estava short mas alvo é long -> fecha e reabre
    assert ("close", "Z", "long") in acts
    assert ("close", "X", "short") in acts
    assert ("open", "X", "long") in acts
    assert ("open", "W", "short") in acts
    # A já está long e continua long -> nenhuma ação
    assert not any(a[1] == "A" for a in acts)
