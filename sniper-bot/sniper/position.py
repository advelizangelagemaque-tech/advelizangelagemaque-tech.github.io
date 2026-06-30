"""Lógica de saída de uma posição em paper-trading.

Decide, a cada atualização de preço, se a posição deve fechar — por
take-profit/stop-loss fixos ou por trailing stop (protege o lucro deixando
o preço correr e só sai quando recua `callback` a partir do pico).
"""

from __future__ import annotations


def update_and_check_exit(trade: dict, price: float, cfg) -> tuple[float | None, str | None]:
    """Atualiza o estado de trailing no `trade` e decide a saída.

    Retorna (exit_price, status) quando deve fechar, ou (None, None) se segue aberta.
    status é "WIN" ou "LOSS" conforme o resultado em relação à entrada.
    """
    long = trade["side"] == "BUY"
    entry = trade["entry"]
    hit_sl = price <= trade["sl"] if long else price >= trade["sl"]

    if not cfg.use_trailing:
        hit_tp = price >= trade["tp"] if long else price <= trade["tp"]
        if hit_tp:
            return trade["tp"], "WIN"
        if hit_sl:
            return trade["sl"], "LOSS"
        return None, None

    # ---- Trailing stop ----
    cb = cfg.trailing_callback_pct
    activation = trade["tp"]  # começa a "trilhar" quando atinge o alvo

    if not trade.get("trail_active"):
        reached = price >= activation if long else price <= activation
        if reached:
            trade["trail_active"] = True
            trade["peak"] = price

    if trade.get("trail_active"):
        if long:
            trade["peak"] = max(trade["peak"], price)
            trail_stop = trade["peak"] * (1 - cb)
            if price <= trail_stop:
                return price, ("WIN" if price > entry else "LOSS")
        else:
            trade["peak"] = min(trade["peak"], price)
            trail_stop = trade["peak"] * (1 + cb)
            if price >= trail_stop:
                return price, ("WIN" if price < entry else "LOSS")

    # Stop-loss "duro" continua valendo (proteção antes da ativação do trailing).
    if hit_sl:
        return trade["sl"], "LOSS"
    return None, None
