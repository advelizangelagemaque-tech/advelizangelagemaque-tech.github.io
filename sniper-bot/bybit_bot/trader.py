"""Execução de ordens na Bybit (perps USDT) via ccxt — abre long com TP/SL.

A matemática de preço (TP/SL/quantidade) é pura e testável. As chamadas de
ordem são best-effort e DEVEM ser validadas por você em testnet antes do real.
"""

from __future__ import annotations

import logging

log = logging.getLogger("bybit_bot.trader")


# ---- matemática pura (testável) --------------------------------------------

def tp_sl_prices(entry: float, tp_roi: float, sl_roi: float, leverage: int) -> tuple[float, float]:
    """Preços de TP/SL para uma posição LONG a partir do ROI e da alavancagem.

    ROI = variação_de_preço * alavancagem  =>  variação = ROI / alavancagem.
    """
    tp = entry * (1 + tp_roi / leverage)
    sl = entry * (1 - sl_roi / leverage)
    return tp, sl


def compute_qty(margin_usdt: float, leverage: int, price: float) -> float:
    """Quantidade de contratos: notional = margem * alavancagem; qty = notional / preço."""
    if price <= 0:
        raise ValueError("Preço inválido.")
    return (margin_usdt * leverage) / price


# ---- cliente e ordem -------------------------------------------------------

def make_client(cfg):
    import ccxt
    ex = ccxt.bybit({
        "apiKey": cfg.api_key, "secret": cfg.api_secret,
        "enableRateLimit": True,
        "options": {"defaultType": "swap"},
    })
    if cfg.use_testnet:
        ex.set_sandbox_mode(True)
    return ex


def open_long(ex, cfg, symbol: str) -> dict:
    """Abre uma posição LONG com TP/SL anexados (server-side na Bybit)."""
    ex.set_leverage(cfg.leverage, symbol)
    ticker = ex.fetch_ticker(symbol)
    price = float(ticker["last"])
    qty = float(ex.amount_to_precision(symbol, compute_qty(cfg.margin_usdt, cfg.leverage, price)))
    tp, sl = tp_sl_prices(price, cfg.tp_roi, cfg.sl_roi, cfg.leverage)
    tp = float(ex.price_to_precision(symbol, tp))
    sl = float(ex.price_to_precision(symbol, sl))

    log.warning("ABRIR LONG %s | qty=%s entry~%.8f TP=%.8f SL=%.8f lev=%dx",
                symbol, qty, price, tp, sl, cfg.leverage)
    order = ex.create_order(symbol, "market", "buy", qty, None, {
        "takeProfit": str(tp), "stopLoss": str(sl), "tpslMode": "Full",
    })
    return {"symbol": symbol, "qty": qty, "entry": price, "tp": tp, "sl": sl,
            "order_id": order.get("id")}


def open_symbols(ex) -> set[str]:
    """Símbolos com posição aberta (para não duplicar)."""
    try:
        positions = ex.fetch_positions()
    except Exception as exc:  # noqa: BLE001
        log.warning("Não consegui listar posições: %s", exc)
        return set()
    out = set()
    for p in positions:
        contracts = p.get("contracts") or p.get("contractSize") or 0
        if contracts and float(contracts) != 0:
            out.add(p.get("symbol"))
    return out
