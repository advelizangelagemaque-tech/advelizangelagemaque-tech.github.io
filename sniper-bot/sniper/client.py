"""Fábrica do cliente Binance Futures (USDⓈ-M), com suporte a testnet."""

from __future__ import annotations

from binance.um_futures import UMFutures

# URL da testnet de futuros USDⓈ-M da Binance.
TESTNET_URL = "https://testnet.binancefuture.com"


def make_client(api_key: str, api_secret: str, use_testnet: bool) -> UMFutures:
    """Cria o cliente apontando para testnet ou produção.

    Em produção, usa a URL padrão da lib (https://fapi.binance.com).
    """
    if use_testnet:
        return UMFutures(key=api_key, secret=api_secret, base_url=TESTNET_URL)
    return UMFutures(key=api_key, secret=api_secret)
