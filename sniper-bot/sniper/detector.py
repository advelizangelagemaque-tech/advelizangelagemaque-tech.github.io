"""Detecção de novas listagens na Binance Futures.

Estratégia: tira um snapshot dos símbolos negociáveis e, a cada poll,
compara com o snapshot anterior para descobrir o que é novo.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger("sniper.detector")


@dataclass(frozen=True)
class SymbolInfo:
    symbol: str
    quote_asset: str
    quantity_precision: int
    price_precision: int
    step_size: float
    tick_size: float
    min_notional: float


def _f(filters: list[dict], ftype: str, key: str, default: str = "0") -> str:
    for fil in filters:
        if fil.get("filterType") == ftype:
            return fil.get(key, default)
    return default


def parse_symbols(exchange_info: dict, quote_asset: str) -> dict[str, SymbolInfo]:
    """Extrai símbolos TRADING perpétuos da moeda de cotação desejada."""
    out: dict[str, SymbolInfo] = {}
    for s in exchange_info.get("symbols", []):
        if s.get("status") != "TRADING":
            continue
        if s.get("quoteAsset") != quote_asset:
            continue
        if s.get("contractType") != "PERPETUAL":
            continue
        filters = s.get("filters", [])
        out[s["symbol"]] = SymbolInfo(
            symbol=s["symbol"],
            quote_asset=s["quoteAsset"],
            quantity_precision=int(s.get("quantityPrecision", 0)),
            price_precision=int(s.get("pricePrecision", 0)),
            step_size=float(_f(filters, "LOT_SIZE", "stepSize", "0")),
            tick_size=float(_f(filters, "PRICE_FILTER", "tickSize", "0")),
            min_notional=float(_f(filters, "MIN_NOTIONAL", "notional", "0")),
        )
    return out


class ListingDetector:
    """Mantém o snapshot e reporta símbolos recém-listados."""

    def __init__(self, quote_asset: str):
        self.quote_asset = quote_asset
        self._known: set[str] = set()
        self._initialized = False

    def prime(self, exchange_info: dict) -> None:
        """Carrega o estado inicial. NÃO dispara trades sobre o que já existe."""
        symbols = parse_symbols(exchange_info, self.quote_asset)
        self._known = set(symbols.keys())
        self._initialized = True
        log.info("Snapshot inicial: %d símbolos %s conhecidos.", len(self._known), self.quote_asset)

    def detect_new(self, exchange_info: dict) -> list[SymbolInfo]:
        """Retorna símbolos que apareceram desde o último snapshot."""
        if not self._initialized:
            raise RuntimeError("Chame prime() antes de detect_new().")
        symbols = parse_symbols(exchange_info, self.quote_asset)
        new_keys = set(symbols.keys()) - self._known
        # Atualiza o conhecido sempre, para não re-disparar no próximo loop.
        self._known |= set(symbols.keys())
        return [symbols[k] for k in sorted(new_keys)]


class PollDetector:
    """Detector por REST polling. Interface comum: start() + poll()."""

    def __init__(self, client, quote_asset: str):
        self.client = client
        self._inner = ListingDetector(quote_asset)

    def start(self) -> None:
        self._inner.prime(self.client.exchange_info())

    def poll(self) -> list[SymbolInfo]:
        return self._inner.detect_new(self.client.exchange_info())

    def stop(self) -> None:  # simetria com o WSDetector
        pass
