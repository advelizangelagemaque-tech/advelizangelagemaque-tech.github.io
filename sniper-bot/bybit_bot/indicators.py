"""Indicadores técnicos (RSI, EMA) e o filtro de confirmação de entrada.

Nada disso "prevê" o futuro — são filtros que evitam entradas ruins:
  - RSI numa faixa saudável (nem esticado/sobrecomprado, nem em queda livre);
  - preço ACIMA da média móvel (a tendência de alta ainda está de pé).
Comprar o dip só quando esses dois confirmam reduz as "facas caindo".
"""

from __future__ import annotations

import logging

log = logging.getLogger("bybit_bot.indicators")


# ---- indicadores puros (testáveis) -----------------------------------------

def rsi(closes: list[float], period: int = 14) -> float | None:
    """RSI clássico (0..100). None se não houver candles suficientes."""
    if len(closes) < period + 1:
        return None
    gains = 0.0
    losses = 0.0
    for i in range(-period, 0):
        diff = closes[i] - closes[i - 1]
        if diff >= 0:
            gains += diff
        else:
            losses -= diff
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def ema(values: list[float], period: int) -> float | None:
    """Média móvel exponencial. None se a lista estiver vazia."""
    if not values:
        return None
    k = 2.0 / (period + 1.0)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1.0 - k)
    return e


def ta_ok(rsi_val: float | None, price: float, ema_val: float | None,
          rsi_min: float, rsi_max: float) -> bool:
    """True se o cenário técnico confirma a entrada (long)."""
    if rsi_val is None or ema_val is None:
        return True  # sem dados suficientes: não bloqueia (fail-open)
    return (rsi_min <= rsi_val <= rsi_max) and (price >= ema_val)


# ---- coleta + avaliação ----------------------------------------------------

def evaluate(ex, symbol: str, cfg) -> dict:
    """Lê candles e diz se o técnico confirma a entrada. Em erro, LIBERA."""
    need = max(cfg.rsi_period + 1, cfg.ema_len) + 3
    try:
        ohlcv = ex.fetch_ohlcv(symbol, cfg.ta_timeframe, limit=need)
    except Exception as exc:  # noqa: BLE001
        log.warning("Sem candles p/ %s (libero): %s", symbol, exc)
        return {"ok": True, "rsi": None, "reason": "sem candles"}
    closes = [c[4] for c in ohlcv]
    if not closes:
        return {"ok": True, "rsi": None, "reason": "sem candles"}
    price = closes[-1]
    r = rsi(closes, cfg.rsi_period)
    e = ema(closes, cfg.ema_len)
    ok = ta_ok(r, price, e, cfg.rsi_min, cfg.rsi_max)
    if ok:
        reason = "técnico ok"
    elif r is not None and r > cfg.rsi_max:
        reason = f"RSI esticado ({r:.0f})"
    elif r is not None and r < cfg.rsi_min:
        reason = f"RSI em queda ({r:.0f})"
    else:
        reason = "preço abaixo da média (tendência fraca)"
    return {"ok": ok, "rsi": r, "reason": reason}
