"""Execução de ordens: entrada a mercado + take-profit + stop-loss.

Suporta modo dry-run (não envia nada, só loga).
"""

from __future__ import annotations

import logging

from binance.um_futures import UMFutures

from .detector import SymbolInfo
from .risk import compute_quantity, tp_sl_prices, validate_order

log = logging.getLogger("sniper.trader")


class Trader:
    def __init__(self, client: UMFutures, cfg, dry_run: bool = False):
        self.client = client
        self.cfg = cfg
        self.dry_run = dry_run

    # ---- helpers de preço ----------------------------------------------------

    def get_mark_price(self, symbol: str) -> float:
        data = self.client.mark_price(symbol=symbol)
        return float(data["markPrice"])

    # ---- ações ---------------------------------------------------------------

    def set_leverage(self, symbol: str) -> None:
        if self.dry_run:
            log.info("[dry-run] set_leverage %s -> %dx", symbol, self.cfg.leverage)
            return
        self.client.change_leverage(symbol=symbol, leverage=self.cfg.leverage)

    def snipe(self, sym: SymbolInfo, side: str = "BUY") -> dict | None:
        """Abre posição no símbolo recém-listado e registra TP/SL.

        Retorna um resumo da operação (ou None em dry-run).
        """
        price = self.get_mark_price(sym.symbol)
        qty = compute_quantity(price, self.cfg.margin_usdt, self.cfg.leverage, sym)
        validate_order(qty, price, sym)
        tp, sl = tp_sl_prices(price, side, self.cfg.take_profit_pct, self.cfg.stop_loss_pct, sym)
        close_side = "SELL" if side == "BUY" else "BUY"

        log.info(
            "SNIPE %s | side=%s qty=%s entry~%.6f TP=%.6f SL=%.6f lev=%dx",
            sym.symbol, side, qty, price, tp, sl, self.cfg.leverage,
        )

        if self.dry_run:
            log.info("[dry-run] nenhuma ordem enviada.")
            return None

        self.set_leverage(sym.symbol)

        entry = self.client.new_order(
            symbol=sym.symbol, side=side, type="MARKET", quantity=qty,
        )
        log.info("Entrada enviada: orderId=%s", entry.get("orderId"))

        # Take-profit (reduceOnly): fecha a posição no lucro.
        self.client.new_order(
            symbol=sym.symbol, side=close_side, type="TAKE_PROFIT_MARKET",
            stopPrice=tp, closePosition=True,
        )
        # Stop-loss (reduceOnly): proteção obrigatória.
        self.client.new_order(
            symbol=sym.symbol, side=close_side, type="STOP_MARKET",
            stopPrice=sl, closePosition=True,
        )
        log.info("TP/SL registrados para %s.", sym.symbol)

        return {
            "symbol": sym.symbol, "side": side, "qty": qty,
            "entry": price, "tp": tp, "sl": sl,
            "entry_order_id": entry.get("orderId"),
        }
