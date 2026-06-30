"""Cálculo de tamanho de posição e arredondamento conforme filtros do símbolo."""

from __future__ import annotations

import math

from .detector import SymbolInfo


def round_step(value: float, step: float) -> float:
    """Arredonda PARA BAIXO no múltiplo de `step` (regra LOT_SIZE da Binance)."""
    if step <= 0:
        return value
    return math.floor(value / step) * step


def round_tick(price: float, tick: float) -> float:
    """Arredonda preço no múltiplo de `tick` (regra PRICE_FILTER)."""
    if tick <= 0:
        return price
    return round(round(price / tick) * tick, 12)


def compute_quantity(price: float, margin_usdt: float, leverage: int, sym: SymbolInfo) -> float:
    """Quantidade de contratos a partir da margem e alavancagem.

    notional = margem * alavancagem ; quantidade = notional / preço,
    arredondada para baixo no stepSize.
    """
    if price <= 0:
        raise ValueError("Preço inválido para cálculo de quantidade.")
    notional = margin_usdt * leverage
    qty = round_step(notional / price, sym.step_size)
    return round(qty, sym.quantity_precision)


def validate_order(qty: float, price: float, sym: SymbolInfo) -> None:
    """Garante que a ordem respeita quantidade mínima e notional mínimo."""
    if qty <= 0:
        raise ValueError("Quantidade calculada é zero. Aumente MARGIN_USDT ou LEVERAGE.")
    notional = qty * price
    if sym.min_notional and notional < sym.min_notional:
        raise ValueError(
            f"Notional {notional:.4f} abaixo do mínimo {sym.min_notional} para {sym.symbol}."
        )


def tp_sl_prices(entry: float, side: str, tp_pct: float, sl_pct: float, sym: SymbolInfo) -> tuple[float, float]:
    """Calcula preços de take-profit e stop-loss arredondados ao tick.

    side: "BUY" (posição long) ou "SELL" (posição short).
    """
    if side == "BUY":
        tp = entry * (1 + tp_pct)
        sl = entry * (1 - sl_pct)
    else:  # SELL / short
        tp = entry * (1 - tp_pct)
        sl = entry * (1 + sl_pct)
    return round_tick(tp, sym.tick_size), round_tick(sl, sym.tick_size)
