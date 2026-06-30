"""Testes do CcxtAdapter usando uma exchange ccxt falsa (sem instalar ccxt)."""

from sniper.ccxt_adapter import CcxtAdapter, _step_from_precision, _decimals_from_step


class FakeExchange:
    """Imita o mínimo da interface ccxt usada pelo adaptador."""

    precisionMode = 2  # DECIMAL_PLACES

    def __init__(self):
        self.markets = {
            "NEW/USDT:USDT": {
                "symbol": "NEW/USDT:USDT", "id": "NEWUSDT", "swap": True,
                "linear": True, "quote": "USDT", "active": True,
                "precision": {"amount": 3, "price": 2},
                "limits": {"cost": {"min": 5}},
            },
            "OLD/USDT:USDT": {  # contrato inativo -> status BREAK
                "symbol": "OLD/USDT:USDT", "id": "OLDUSDT", "swap": True,
                "linear": True, "quote": "USDT", "active": False,
                "precision": {"amount": 3, "price": 2}, "limits": {},
            },
            "SPOT/USDT": {  # não é swap -> ignorado
                "symbol": "SPOT/USDT", "swap": False, "quote": "USDT",
                "precision": {}, "limits": {},
            },
            "COIN/BUSD:BUSD": {  # outra cotação -> ignorado
                "symbol": "COIN/BUSD:BUSD", "swap": True, "linear": True,
                "quote": "BUSD", "active": True, "precision": {}, "limits": {},
            },
        }
        self.orders = []

    def load_markets(self):
        return self.markets

    def fetch_ticker(self, symbol):
        return {"last": 2.0, "quoteVolume": 123456.0}

    def fetch_order_book(self, symbol, limit=20):
        return {"bids": [[1.99, 1000]], "asks": [[2.00, 1000]]}

    def set_leverage(self, leverage, symbol):
        return {"leverage": leverage, "symbol": symbol}

    def create_order(self, symbol, type, side, amount, price=None, params=None):
        o = {"symbol": symbol, "type": type, "side": side, "amount": amount,
             "price": price, "params": params or {}}
        self.orders.append(o)
        return {"id": len(self.orders), **o}


def test_conversao_precision():
    assert _step_from_precision(3, 2) == 0.001        # 3 casas decimais
    assert _step_from_precision(0.01, 4) == 0.01      # modo TICK_SIZE
    assert _decimals_from_step(0.001) == 3


def test_exchange_info_filtra_e_converte():
    a = CcxtAdapter(FakeExchange(), "USDT")
    info = a.exchange_info()
    syms = {s["symbol"]: s for s in info["symbols"]}
    # só os swaps USDT entram (NEW ativo + OLD inativo); spot e BUSD ficam de fora
    assert set(syms) == {"NEW/USDT:USDT", "OLD/USDT:USDT"}
    new = syms["NEW/USDT:USDT"]
    assert new["status"] == "TRADING"
    assert syms["OLD/USDT:USDT"]["status"] == "BREAK"
    f = {x["filterType"]: x for x in new["filters"]}
    assert f["LOT_SIZE"]["stepSize"] == "0.001"
    assert f["PRICE_FILTER"]["tickSize"] == "0.01"
    assert f["MIN_NOTIONAL"]["notional"] == "5"


def test_mark_price_e_depth_e_volume():
    a = CcxtAdapter(FakeExchange(), "USDT")
    assert a.mark_price("NEW/USDT:USDT") == {"markPrice": "2.0"}
    book = a.depth("NEW/USDT:USDT", 20)
    assert book["bids"] == [[1.99, 1000]] and book["asks"] == [[2.00, 1000]]
    assert float(a.ticker_24hr_price_change("NEW/USDT:USDT")["quoteVolume"]) == 123456.0


def test_new_order_market_e_protecao():
    ex = FakeExchange()
    a = CcxtAdapter(ex, "USDT")
    a.new_order(symbol="NEW/USDT:USDT", side="BUY", type="MARKET", quantity=30)
    a.new_order(symbol="NEW/USDT:USDT", side="SELL", type="STOP_MARKET",
                stopPrice=1.9, closePosition="true", quantity=30)
    assert ex.orders[0]["type"] == "market" and ex.orders[0]["side"] == "buy"
    assert ex.orders[1]["params"]["stopPrice"] == 1.9
    assert ex.orders[1]["params"]["reduceOnly"] is True


def test_adapter_funciona_com_quality_e_detector():
    """Integração: detector e filtro de qualidade sobre o adaptador."""
    from sniper.detector import PollDetector
    from sniper.quality import check_quality
    from tests.conftest import make_cfg

    a = CcxtAdapter(FakeExchange(), "USDT")
    det = PollDetector(a, "USDT")
    det.start()                       # snapshot inicial (NEW + OLD já existem)
    assert det.poll() == []           # nada novo
    # filtro de qualidade roda sobre o símbolo do adaptador
    info = a.exchange_info()
    from sniper.detector import parse_symbols
    sym = parse_symbols(info, "USDT")["NEW/USDT:USDT"]
    ok, reason, _ = check_quality(a, sym, make_cfg(min_book_depth_usdt=1000))
    assert ok, reason
