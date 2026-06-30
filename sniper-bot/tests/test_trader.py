"""Testes do Trader nos modos dry/paper/live (com cliente falso)."""

from sniper.trader import Trader
from tests.conftest import FakeClient, make_cfg


def _types(orders):
    return [o["type"] for o in orders]


def test_dry_nao_envia_nada(cfg, sym):
    client = FakeClient(mark_price=2.0)
    t = Trader(client, cfg, mode="dry")
    assert t.snipe(sym) is None
    assert client.orders == []


def test_paper_simula_sem_ordens(cfg, sym):
    client = FakeClient(mark_price=2.0)
    trade = Trader(client, cfg, mode="paper").snipe(sym, side="BUY")
    assert client.orders == []
    assert trade["symbol"] == "NEWUSDT"
    assert trade["qty"] == 30.0
    assert trade["entry"] == 2.0
    assert trade["tp"] == 2.2 and trade["sl"] == 1.9


def test_live_fixo_envia_market_sl_tp(cfg, sym):
    client = FakeClient(mark_price=2.0)
    Trader(client, cfg, mode="live").snipe(sym, side="BUY")
    assert client.leverage_calls == [{"symbol": "NEWUSDT", "leverage": 3}]
    assert _types(client.orders) == ["MARKET", "STOP_MARKET", "TAKE_PROFIT_MARKET"]
    market = client.orders[0]
    assert market["side"] == "BUY" and market["quantity"] == 30.0
    # ordens de saída no lado oposto
    assert client.orders[1]["side"] == "SELL"
    # closePosition precisa ser a string "true" (Binance rejeita o bool "True")
    assert client.orders[1]["closePosition"] == "true"
    assert client.orders[2]["closePosition"] == "true"


def test_live_trailing_usa_trailing_stop(sym):
    cfg = make_cfg(use_trailing=True, trailing_callback_pct=0.012)
    client = FakeClient(mark_price=2.0)
    Trader(client, cfg, mode="live").snipe(sym, side="BUY")
    assert _types(client.orders) == ["MARKET", "STOP_MARKET", "TRAILING_STOP_MARKET"]
    trailing = client.orders[2]
    assert trailing["callbackRate"] == 1.2   # 0.012 -> 1.2%
    assert trailing["activationPrice"] == 2.2
    assert trailing["reduceOnly"] == "true"


def test_short_inverte_lados(cfg, sym):
    client = FakeClient(mark_price=2.0)
    Trader(client, cfg, mode="live").snipe(sym, side="SELL")
    assert client.orders[0]["side"] == "SELL"   # entrada short
    assert client.orders[1]["side"] == "BUY"    # saída no lado oposto
