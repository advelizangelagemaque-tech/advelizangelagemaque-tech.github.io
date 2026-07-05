"""Backtester: testa a regra do Sniper (dip em alta + RSI/EMA + TP/SL) no PASSADO.

Sem dinheiro, sem risco: baixa candles históricos de vários perps e simula, vela
a vela, o que a estratégia teria feito. Diz a taxa de acerto e a expectativa REAL
em dados passados — pra sabermos se tem borda ANTES de operar com dinheiro.

    python -m bybit_bot.backtest --top 40 --days 7
"""

from __future__ import annotations

import argparse
import logging

from .indicators import ema, rsi, ta_ok
from .screener import compute_dip
from .trader import tp_sl_prices

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("bybit_bot.backtest")


# ---- simulação pura (testável) ---------------------------------------------

def simulate_symbol(ohlcv: list, p: dict) -> list[dict]:
    """Simula a estratégia num histórico [ts,o,h,l,c,v]. Retorna trades {outcome, roi}.

    Regra: entra quando há dip de p[dip_min..dip_max] a partir da máxima recente,
    RSI saudável e preço acima da EMA. Sai no TP ou SL (SL tem prioridade se ambos
    caírem na mesma vela — pessimista, pra não enganar). Desconta taxa por trade.
    """
    if len(ohlcv) < p["lookback"] + 2:
        return []
    highs = [c[2] for c in ohlcv]
    lows = [c[3] for c in ohlcv]
    closes = [c[4] for c in ohlcv]
    trades: list[dict] = []
    open_t = None
    i = p["lookback"]
    while i < len(ohlcv):
        if open_t is None:
            price = closes[i]
            dip = compute_dip(highs[i - p["lookback"]:i], price)
            r = rsi(closes[:i + 1], p["rsi_period"])
            e = ema(closes[:i + 1], p["ema_len"])
            if p["dip_min"] <= dip <= p["dip_max"] and ta_ok(r, price, e, p["rsi_min"], p["rsi_max"]):
                tp, sl = tp_sl_prices(price, p["tp_roi"], p["sl_roi"], p["leverage"])
                open_t = {"entry": price, "tp": tp, "sl": sl}
        else:
            hit = None
            if lows[i] <= open_t["sl"]:
                hit = ("SL", -p["sl_roi"])
            elif highs[i] >= open_t["tp"]:
                hit = ("TP", p["tp_roi"])
            if hit:
                roi = hit[1] - p["fee_roi"]
                trades.append({"outcome": hit[0], "roi": roi})
                open_t = None
        i += 1
    return trades


def aggregate(trades: list[dict]) -> dict:
    """Estatísticas do backtest (em ROI, já com taxa descontada)."""
    n = len(trades)
    if n == 0:
        return {"count": 0, "win_rate": 0.0, "total_roi": 0.0, "expectancy": 0.0,
                "profit_factor": 0.0, "wins": 0, "losses": 0}
    wins = [t["roi"] for t in trades if t["roi"] > 0]
    losses = [t["roi"] for t in trades if t["roi"] <= 0]
    gross_w = sum(wins)
    gross_l = -sum(losses)
    total = sum(t["roi"] for t in trades)
    return {
        "count": n, "wins": len(wins), "losses": len(losses),
        "win_rate": len(wins) / n,
        "total_roi": total,
        "expectancy": total / n,
        "profit_factor": (gross_w / gross_l) if gross_l > 0 else float("inf"),
    }


# ---- coleta e execução -----------------------------------------------------

def _public_client():
    import ccxt
    return ccxt.bybit({"options": {"defaultType": "swap"}, "enableRateLimit": True})


def _top_symbols(ex, top: int, min_vol: float) -> list[str]:
    tickers = ex.fetch_tickers()
    rows = []
    for s, t in tickers.items():
        if not s.endswith(":USDT"):
            continue
        vol = t.get("quoteVolume") or 0
        if vol and float(vol) >= min_vol:
            rows.append((s, float(vol)))
    rows.sort(key=lambda x: -x[1])
    return [s for s, _ in rows[:top]]


def run_backtest(p: dict, top: int, days: int, min_vol: float) -> int:
    ex = _public_client()
    tf_min = 5
    limit = min(1000, int(days * 24 * 60 / tf_min))
    symbols = _top_symbols(ex, top, min_vol)
    log.info("Backtest | %d símbolos | %d dias | dip %.0f-%.0f%% | TP+%.0f%%/SL-%.0f%% ROI | %dx | taxa %.2f%%",
             len(symbols), days, p["dip_min"] * 100, p["dip_max"] * 100,
             p["tp_roi"] * 100, p["sl_roi"] * 100, p["leverage"], p["fee_roi"] * 100)
    all_trades: list[dict] = []
    for s in symbols:
        try:
            ohlcv = ex.fetch_ohlcv(s, "5m", limit=limit)
        except Exception:  # noqa: BLE001
            continue
        all_trades.extend(simulate_symbol(ohlcv, p))

    st = aggregate(all_trades)
    print("=" * 56)
    print("RESULTADO DO BACKTEST (Sniper: dip em alta + RSI/EMA)")
    print("=" * 56)
    if st["count"] == 0:
        print("Nenhum trade disparou no período (regra muito restritiva ou poucos dados).")
        return 0
    pf = "inf" if st["profit_factor"] == float("inf") else f"{st['profit_factor']:.2f}"
    print(f"Trades simulados : {st['count']}")
    print(f"Acertos          : {st['wins']}  ({st['win_rate'] * 100:.0f}%)")
    print(f"Perdas           : {st['losses']}")
    print(f"Expectativa/trade: {st['expectancy'] * 100:+.2f}% ROI")
    print(f"ROI acumulado    : {st['total_roi'] * 100:+.0f}%  (soma de todos os trades)")
    print(f"Profit factor    : {pf}")
    print("-" * 56)
    if st["expectancy"] > 0 and st["profit_factor"] > 1:
        print("✅ Borda POSITIVA no histórico — a regra deu lucro nesses dados.")
    else:
        print("❌ Borda NEGATIVA no histórico — a regra teria perdido. Rever antes do real.")
    print("=" * 56)
    return 0


def _params(args) -> dict:
    return {
        "dip_min": args.dip_min, "dip_max": args.dip_max,
        "tp_roi": args.tp, "sl_roi": args.sl, "leverage": args.lev,
        "rsi_period": 14, "rsi_min": args.rsi_min, "rsi_max": args.rsi_max,
        "ema_len": args.ema, "lookback": args.lookback,
        "fee_roi": args.fee,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Backtester do Sniper (dados históricos)")
    ap.add_argument("--top", type=int, default=40, help="Nº de perps (por volume) a testar.")
    ap.add_argument("--days", type=int, default=7, help="Dias de histórico (5m).")
    ap.add_argument("--min-vol", type=float, default=5_000_000)
    ap.add_argument("--dip-min", type=float, default=0.03)
    ap.add_argument("--dip-max", type=float, default=0.06)
    ap.add_argument("--tp", type=float, default=0.30)
    ap.add_argument("--sl", type=float, default=0.15)
    ap.add_argument("--lev", type=int, default=5)
    ap.add_argument("--rsi-min", type=float, default=40.0)
    ap.add_argument("--rsi-max", type=float, default=72.0)
    ap.add_argument("--ema", type=int, default=20)
    ap.add_argument("--lookback", type=int, default=12)
    ap.add_argument("--fee", type=float, default=0.006, help="Taxa por trade em ROI (0.006 = 0.6%%).")
    args = ap.parse_args()
    return run_backtest(_params(args), args.top, args.days, args.min_vol)


if __name__ == "__main__":
    import sys
    sys.exit(main())
