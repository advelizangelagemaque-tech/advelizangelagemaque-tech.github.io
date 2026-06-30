"""Detector de listagens via WebSocket (mais rápido que REST polling).

Assina o stream de todos os tickers (`!ticker@arr`) da Binance Futures.
Quando aparece um símbolo que não estava no snapshot inicial, ele é
enfileirado; o loop principal busca os filtros via REST e dispara o snipe.

Observação: a API de WebSocket do `binance-futures-connector` mudou entre
versões. Este módulo usa `subscribe(stream=[...])`, que é estável nas v3/v4,
e um handler tolerante à assinatura do callback. Se a sua versão não expuser
`subscribe`, use o modo `--mode poll` (REST) como fallback.
"""

from __future__ import annotations

import json
import logging
import queue

from binance.websocket.um_futures.websocket_client import UMFuturesWebsocketClient

from .detector import SymbolInfo, parse_symbols

log = logging.getLogger("sniper.ws")


class WSDetector:
    """Detector por WebSocket. Interface comum: start() + poll()."""

    def __init__(self, client, quote_asset: str):
        self.client = client          # cliente REST, p/ buscar filtros do símbolo
        self.quote_asset = quote_asset
        self._known: set[str] = set()
        self._queue: "queue.Queue[str]" = queue.Queue()
        self._ws: UMFuturesWebsocketClient | None = None

    # ---- ciclo de vida -------------------------------------------------------

    def start(self) -> None:
        info = self.client.exchange_info()
        self._known = set(parse_symbols(info, self.quote_asset).keys())
        log.info("Snapshot inicial (WS): %d símbolos conhecidos.", len(self._known))
        self._ws = UMFuturesWebsocketClient(on_message=self._on_message)
        # Stream com array de todos os tickers do mercado.
        self._ws.subscribe(stream=["!ticker@arr"])
        log.info("WebSocket assinado em !ticker@arr.")

    def stop(self) -> None:
        if self._ws is not None:
            try:
                self._ws.stop()
            except Exception:  # noqa: BLE001
                pass

    # ---- callback do WebSocket (roda em outra thread) ------------------------

    def _on_message(self, *args) -> None:
        message = args[-1]  # tolera assinaturas (msg) ou (socket, msg)
        try:
            data = json.loads(message) if isinstance(message, str) else message
        except (ValueError, TypeError):
            return
        if isinstance(data, dict):
            # mensagens de controle (ex.: resultado do subscribe) não têm 'data'
            data = data.get("data")
        if not isinstance(data, list):
            return
        for item in data:
            sym = item.get("s")
            if not sym or sym in self._known:
                continue
            if not sym.endswith(self.quote_asset):
                continue
            self._known.add(sym)
            log.warning("WS detectou símbolo novo: %s", sym)
            self._queue.put(sym)

    # ---- consumido pelo loop principal --------------------------------------

    def poll(self) -> list[SymbolInfo]:
        """Drena a fila e resolve os filtros de cada símbolo novo via REST."""
        names: list[str] = []
        while True:
            try:
                names.append(self._queue.get_nowait())
            except queue.Empty:
                break
        if not names:
            return []
        # Uma única chamada REST resolve os filtros de todos os novos.
        symbols = parse_symbols(self.client.exchange_info(), self.quote_asset)
        out = [symbols[n] for n in names if n in symbols]
        missing = [n for n in names if n not in symbols]
        if missing:
            # Ainda não está como PERPETUAL/TRADING no exchangeInfo; tenta de novo depois.
            # Mantém em _known (para o WS não reenfileirar) e só recoloca na fila.
            for n in missing:
                self._queue.put(n)
        return out
