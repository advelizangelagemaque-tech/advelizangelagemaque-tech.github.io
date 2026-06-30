"""Adaptador para outras CEXs (Bybit, OKX, ...) via biblioteca ccxt.

Expõe a MESMA interface que o conector nativo da Binance usa (exchange_info,
mark_price, depth, ticker_24hr_price_change, change_leverage, new_order), de
modo que detector/quality/trader funcionam sem alteração. Suporta o modo
polling (não WebSocket) — para sniping de listagem em paper-trading e live.

Observação: o roteamento de ordens de proteção (SL/TP/trailing) no modo LIVE
varia por exchange e deve ser validado por você em testnet antes do real. A
detecção e o paper-trading funcionam igual em qualquer CEX suportada pela ccxt.
"""

from __future__ import annotations

import logging
import math

log = logging.getLogger("sniper.ccxt")

# Valor da constante ccxt.TICK_SIZE (modo em que a "precisão" já é o passo).
_TICK_SIZE_MODE = 4


def _step_from_precision(prec, mode) -> float:
    """Converte a 'precision' da ccxt em tamanho de passo (step/tick)."""
    if prec in (None, ""):
        return 0.0
    prec = float(prec)
    if mode == _TICK_SIZE_MODE:
        return prec                      # já é o passo (ex. 0.001)
    return 10 ** (-int(prec))            # casas decimais -> passo


def _decimals_from_step(step: float) -> int:
    if step <= 0:
        return 8
    return max(0, int(round(-math.log10(step))))


class CcxtAdapter:
    """Cliente compatível com a interface usada pelo bot, backed by ccxt."""

    def __init__(self, exchange, quote_asset: str = "USDT"):
        self.exchange = exchange
        self.quote_asset = quote_asset
        self.mode = getattr(exchange, "precisionMode", 2)
        if not getattr(exchange, "markets", None):
            self.exchange.load_markets()

    @classmethod
    def create(cls, exchange_id: str, api_key: str, api_secret: str,
               use_testnet: bool, quote_asset: str = "USDT") -> "CcxtAdapter":
        import ccxt  # import tardio: só exigido para CEXs não-Binance
        klass = getattr(ccxt, exchange_id)
        ex = klass({
            "apiKey": api_key, "secret": api_secret,
            "enableRateLimit": True,
            "options": {"defaultType": "swap"},  # futuros perpétuos
        })
        if use_testnet:
            ex.set_sandbox_mode(True)
        ex.load_markets()
        return cls(ex, quote_asset)

    # ---- interface estilo Binance-connector -------------------------------

    def exchange_info(self) -> dict:
        symbols = []
        for m in self.exchange.markets.values():
            if not m.get("swap"):
                continue
            if m.get("linear") is False:           # queremos margem em USDT (linear)
                continue
            if m.get("quote") != self.quote_asset:
                continue
            prec = m.get("precision", {}) or {}
            step = _step_from_precision(prec.get("amount"), self.mode)
            tick = _step_from_precision(prec.get("price"), self.mode)
            cost_min = ((m.get("limits", {}) or {}).get("cost", {}) or {}).get("min") or 0
            symbols.append({
                "symbol": m["symbol"],             # símbolo unificado da ccxt
                "status": "TRADING" if m.get("active", True) else "BREAK",
                "quoteAsset": m.get("quote"),
                "contractType": "PERPETUAL",
                "quantityPrecision": _decimals_from_step(step) if step else 8,
                "pricePrecision": _decimals_from_step(tick) if tick else 8,
                "filters": [
                    {"filterType": "LOT_SIZE", "stepSize": str(step)},
                    {"filterType": "PRICE_FILTER", "tickSize": str(tick)},
                    {"filterType": "MIN_NOTIONAL", "notional": str(cost_min)},
                ],
            })
        return {"symbols": symbols}

    def mark_price(self, symbol: str) -> dict:
        t = self.exchange.fetch_ticker(symbol)
        price = t.get("last") or t.get("close") or (t.get("info", {}) or {}).get("markPrice")
        return {"markPrice": str(price)}

    def depth(self, symbol: str, limit: int = 20) -> dict:
        ob = self.exchange.fetch_order_book(symbol, limit)
        return {"bids": ob.get("bids", []), "asks": ob.get("asks", [])}

    def ticker_24hr_price_change(self, symbol: str) -> dict:
        t = self.exchange.fetch_ticker(symbol)
        return {"quoteVolume": t.get("quoteVolume") or 0}

    def change_leverage(self, symbol: str, leverage: int):
        try:
            return self.exchange.set_leverage(leverage, symbol)
        except Exception as exc:  # noqa: BLE001
            log.warning("set_leverage falhou em %s: %s", symbol, exc)

    def new_order(self, **kw):
        symbol = kw["symbol"]
        side = kw["side"].lower()
        otype = kw["type"]
        if otype == "MARKET":
            return self.exchange.create_order(symbol, "market", side, kw["quantity"])

        # Ordens de proteção (best-effort; validar por exchange em testnet).
        params = {"reduceOnly": True}
        if otype in ("STOP_MARKET", "TAKE_PROFIT_MARKET"):
            params["stopPrice"] = kw["stopPrice"]
            if kw.get("closePosition"):
                params["closePosition"] = True
            return self.exchange.create_order(symbol, "market", side, kw.get("quantity"), None, params)
        if otype == "TRAILING_STOP_MARKET":
            params["callbackRate"] = kw["callbackRate"]
            params["activationPrice"] = kw["activationPrice"]
            return self.exchange.create_order(symbol, "market", side, kw["quantity"], None, params)
        raise ValueError(f"Tipo de ordem não suportado no adaptador ccxt: {otype}")
