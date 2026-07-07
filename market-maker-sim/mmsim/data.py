"""Busca candles reais (só leitura, sem chave) para o simulador rodar em preços
de verdade. Usa ccxt — o mesmo dos outros bots."""

from __future__ import annotations


def fetch_ohlcv(symbol: str, timeframe: str = "1m", limit: int = 1000,
                exchange: str = "bybit") -> list:
    try:
        import ccxt
    except ImportError:
        raise SystemExit("ccxt não está instalado. Rode:  pip install ccxt")
    cls = getattr(ccxt, exchange, None)
    if cls is None:
        raise SystemExit(f"Corretora desconhecida: {exchange}")
    ex = cls({"enableRateLimit": True, "options": {"defaultType": "swap"}})
    return ex.fetch_ohlcv(symbol, timeframe, limit=limit)
