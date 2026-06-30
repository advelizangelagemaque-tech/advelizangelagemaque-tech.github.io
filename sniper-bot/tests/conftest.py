"""Fixtures e dublês compartilhados pelos testes."""

from __future__ import annotations

import pytest

from sniper.config import Config
from sniper.detector import SymbolInfo


class FakeClient:
    """Cliente Binance falso: registra chamadas e devolve respostas controladas."""

    def __init__(self, mark_price=2.0, bids=None, asks=None, symbols=None, quote_volume=0.0):
        self._mark_price = mark_price
        self._bids = bids if bids is not None else [["1.99", "1000"]]
        self._asks = asks if asks is not None else [["2.00", "1000"]]
        self._symbols = symbols  # dict exchange_info ou None
        self._quote_volume = quote_volume
        self.orders: list[dict] = []
        self.leverage_calls: list[dict] = []

    def mark_price(self, symbol):
        return {"markPrice": str(self._mark_price)}

    def depth(self, symbol, limit):
        return {"bids": self._bids, "asks": self._asks}

    def ticker_24hr(self, symbol):
        return {"quoteVolume": str(self._quote_volume)}

    def change_leverage(self, symbol, leverage):
        self.leverage_calls.append({"symbol": symbol, "leverage": leverage})

    def new_order(self, **kwargs):
        self.orders.append(kwargs)
        return {"orderId": len(self.orders)}

    def exchange_info(self):
        return self._symbols if self._symbols is not None else {"symbols": []}


def make_cfg(**overrides) -> Config:
    """Cria uma Config válida; sobrescreve campos pelos kwargs."""
    base = dict(
        api_key="k", api_secret="s", use_testnet=True,
        margin_usdt=20.0, leverage=3,
        take_profit_pct=0.10, stop_loss_pct=0.05,
        quote_asset="USDT", poll_interval_ms=500, max_trades=1,
        max_spread_pct=0.03, min_book_depth_usdt=1000.0, min_quote_volume=0.0,
        use_trailing=False, trailing_callback_pct=0.01,
        cooldown_seconds=0, telegram_token="", telegram_chat_id="",
    )
    base.update(overrides)
    cfg = Config(**base)
    cfg.validate()
    return cfg


@pytest.fixture
def cfg():
    return make_cfg()


@pytest.fixture
def sym():
    return SymbolInfo(
        symbol="NEWUSDT", quote_asset="USDT",
        quantity_precision=3, price_precision=2,
        step_size=0.001, tick_size=0.01, min_notional=5.0,
    )


def exchange_info(symbols, status="TRADING", contract="PERPETUAL", quote="USDT"):
    """Monta um exchange_info de teste a partir de uma lista de símbolos."""
    return {"symbols": [
        {
            "symbol": s, "status": status, "quoteAsset": quote, "contractType": contract,
            "quantityPrecision": 3, "pricePrecision": 2,
            "filters": [
                {"filterType": "LOT_SIZE", "stepSize": "0.001"},
                {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                {"filterType": "MIN_NOTIONAL", "notional": "5"},
            ],
        } for s in symbols
    ]}
