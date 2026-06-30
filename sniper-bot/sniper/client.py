"""Fábrica do cliente da exchange.

- Binance: usa o conector nativo UMFutures (mais rápido, com WebSocket).
- Demais CEXs (bybit, okx, ...): usa o CcxtAdapter (modo polling).
"""

from __future__ import annotations

# URL da testnet de futuros USDⓈ-M da Binance.
TESTNET_URL = "https://testnet.binancefuture.com"


def make_client(cfg):
    """Cria o cliente conforme cfg.exchange."""
    if cfg.exchange == "binance":
        from binance.um_futures import UMFutures
        if cfg.use_testnet:
            return UMFutures(key=cfg.api_key, secret=cfg.api_secret, base_url=TESTNET_URL)
        return UMFutures(key=cfg.api_key, secret=cfg.api_secret)

    # Outras CEXs via ccxt.
    from .ccxt_adapter import CcxtAdapter
    return CcxtAdapter.create(
        exchange_id=cfg.exchange, api_key=cfg.api_key, api_secret=cfg.api_secret,
        use_testnet=cfg.use_testnet, quote_asset=cfg.quote_asset,
    )
