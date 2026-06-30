"""Filtro de qualidade da listagem.

Antes de snipar, avalia se o mercado tem liquidez mínima e spread aceitável.
Evita entrar em listagem "podre" (livro raso, spread enorme), onde o slippage
e a impossibilidade de sair devoram qualquer ganho.

Cada limite com valor 0 é considerado DESLIGADO.
"""

from __future__ import annotations

import logging

from .detector import SymbolInfo

log = logging.getLogger("sniper.quality")


def _book_notional(levels: list[list[str]]) -> float:
    """Soma preço*quantidade de cada nível do livro (em USDT)."""
    return sum(float(p) * float(q) for p, q in levels)


def check_quality(client, sym: SymbolInfo, cfg) -> tuple[bool, str, dict]:
    """Retorna (aprovado, motivo, métricas).

    Métricas: best_bid, best_ask, spread_pct, book_depth_usdt, quote_volume.
    """
    metrics: dict = {}

    # ---- Livro de ofertas: spread e profundidade ----
    book = client.depth(symbol=sym.symbol, limit=20)
    bids = book.get("bids", [])
    asks = book.get("asks", [])
    if not bids or not asks:
        return False, "livro vazio (sem bids/asks)", metrics

    best_bid = float(bids[0][0])
    best_ask = float(asks[0][0])
    mid = (best_bid + best_ask) / 2
    spread_pct = (best_ask - best_bid) / mid if mid > 0 else 1.0
    depth_usdt = _book_notional(bids) + _book_notional(asks)
    metrics.update(best_bid=best_bid, best_ask=best_ask,
                   spread_pct=spread_pct, book_depth_usdt=depth_usdt)

    if cfg.max_spread_pct > 0 and spread_pct > cfg.max_spread_pct:
        return False, f"spread {spread_pct:.2%} > máx {cfg.max_spread_pct:.2%}", metrics
    if cfg.min_book_depth_usdt > 0 and depth_usdt < cfg.min_book_depth_usdt:
        return False, f"profundidade {depth_usdt:.0f} < mín {cfg.min_book_depth_usdt:.0f} USDT", metrics

    # ---- Volume 24h (opcional; numa listagem nova costuma ser baixo) ----
    if cfg.min_quote_volume > 0:
        tk = client.ticker_24hr_price_change(symbol=sym.symbol)
        quote_vol = float(tk.get("quoteVolume", 0))
        metrics["quote_volume"] = quote_vol
        if quote_vol < cfg.min_quote_volume:
            return False, f"volume 24h {quote_vol:.0f} < mín {cfg.min_quote_volume:.0f} USDT", metrics

    return True, "aprovado", metrics
