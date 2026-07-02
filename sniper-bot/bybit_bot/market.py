"""Análise de mercado (filtro macro): só compra quando o cenário ajuda.

Ideia: comprar o dip de um token em alta é bom, MAS não no meio de uma queda
geral do mercado. Antes de abrir, o agente olha:
  - a variação do BTC em 24h (termômetro do mercado);
  - a amplitude: quantos perps estão no positivo hoje (risk-on vs risk-off).
Se o mercado está claramente ruim, ele PAUSA novas compras (não fecha as abertas —
essas seguem com seu TP/SL na Bybit).
"""

from __future__ import annotations

import logging

log = logging.getLogger("bybit_bot.market")

BTC_SYMBOL = "BTC/USDT:USDT"


# ---- lógica pura (testável) ------------------------------------------------

def compute_breadth(tickers: dict) -> float:
    """Fração de perps USDT com variação 24h positiva (0..1)."""
    total = 0
    up = 0
    for sym, t in tickers.items():
        if not sym.endswith(":USDT"):
            continue
        pct = t.get("percentage")
        if pct is None:
            continue
        total += 1
        if pct > 0:
            up += 1
    return (up / total) if total else 0.0


def btc_change(tickers: dict, symbol: str = BTC_SYMBOL) -> float:
    """Variação do BTC em 24h como fração (0.02 = +2%). 0 se não achar."""
    t = tickers.get(symbol)
    if not t:
        return 0.0
    pct = t.get("percentage")
    return (pct / 100.0) if pct is not None else 0.0


def regime_ok(btc_pct: float, breadth: float, btc_min: float, breadth_min: float) -> bool:
    """True se o mercado permite abrir novas posições long."""
    return btc_pct >= btc_min and breadth >= breadth_min


# ---- coleta (rede) ---------------------------------------------------------

def evaluate(ex, cfg) -> dict:
    """Lê o mercado agora e diz se pode comprar. Em erro, LIBERA (fail-open)."""
    try:
        tickers = ex.fetch_tickers()
    except Exception as exc:  # noqa: BLE001
        log.warning("Não consegui ler o mercado (libero por segurança): %s", exc)
        return {"ok": True, "btc_pct": 0.0, "breadth": 0.0, "reason": "sem dados de mercado"}
    btc = btc_change(tickers)
    breadth = compute_breadth(tickers)
    ok = regime_ok(btc, breadth, cfg.btc_min_24h, cfg.breadth_min)
    if ok:
        reason = "mercado ok"
    elif btc < cfg.btc_min_24h:
        reason = f"BTC caindo ({btc * 100:+.1f}% em 24h)"
    else:
        reason = f"poucos tokens no positivo ({breadth * 100:.0f}%)"
    return {"ok": ok, "btc_pct": btc, "breadth": breadth, "reason": reason}
