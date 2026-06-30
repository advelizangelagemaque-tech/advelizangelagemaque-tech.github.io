"""Execução de ordens: entrada a mercado + take-profit + stop-loss.

Modos:
- live : envia ordens de verdade (testnet ou produção, conforme config).
- paper: NÃO envia ordens; simula a entrada e devolve o trade para o
         loop principal acompanhar TP/SL com o preço real (forward test).
- dry  : apenas loga a intenção e não registra nada.
"""

from __future__ import annotations

import logging

from binance.um_futures import UMFutures

from .detector import SymbolInfo
from .risk import compute_quantity, tp_sl_prices, validate_order

log = logging.getLogger("sniper.trader")


class Trader:
    def __init__(self, client: UMFutures, cfg, mode: str = "live"):
        assert mode in {"live", "paper", "dry"}
        self.client = client
        self.cfg = cfg
        self.mode = mode

    # ---- helpers de preço ----------------------------------------------------

    def get_mark_price(self, symbol: str) -> float:
        data = self.client.mark_price(symbol=symbol)
        return float(data["markPrice"])

    # ---- ações ---------------------------------------------------------------

    def _build_trade(self, sym: SymbolInfo, side: str) -> dict:
        price = self.get_mark_price(sym.symbol)
        qty = compute_quantity(price, self.cfg.margin_usdt, self.cfg.leverage, sym)
        validate_order(qty, price, sym)
        tp, sl = tp_sl_prices(price, side, self.cfg.take_profit_pct, self.cfg.stop_loss_pct, sym)
        return {
            "symbol": sym.symbol, "side": side,
            "close_side": "SELL" if side == "BUY" else "BUY",
            "qty": qty, "entry": price, "tp": tp, "sl": sl,
            "leverage": self.cfg.leverage, "margin_usdt": self.cfg.margin_usdt,
        }

    def snipe(self, sym: SymbolInfo, side: str = "BUY") -> dict | None:
        """Abre a posição no símbolo recém-listado. Retorna o trade (ou None em dry)."""
        trade = self._build_trade(sym, side)
        log.info(
            "SNIPE[%s] %s | side=%s qty=%s entry~%.6f TP=%.6f SL=%.6f lev=%dx",
            self.mode, sym.symbol, side, trade["qty"], trade["entry"],
            trade["tp"], trade["sl"], self.cfg.leverage,
        )

        if self.mode == "dry":
            log.info("[dry] nenhuma ordem enviada, nada registrado.")
            return None
        if self.mode == "paper":
            log.info("[paper] entrada simulada; acompanhando TP/SL com preço real.")
            return trade

        # ---- live ----
        self.client.change_leverage(symbol=sym.symbol, leverage=self.cfg.leverage)
        entry = self.client.new_order(
            symbol=sym.symbol, side=side, type="MARKET", quantity=trade["qty"],
        )
        log.info("Entrada enviada: orderId=%s", entry.get("orderId"))
        self.client.new_order(
            symbol=sym.symbol, side=trade["close_side"], type="TAKE_PROFIT_MARKET",
            stopPrice=trade["tp"], closePosition=True,
        )
        self.client.new_order(
            symbol=sym.symbol, side=trade["close_side"], type="STOP_MARKET",
            stopPrice=trade["sl"], closePosition=True,
        )
        log.info("TP/SL registrados para %s.", sym.symbol)
        trade["entry_order_id"] = entry.get("orderId")
        return trade
