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


# ---- indicadores rolantes O(N) (rápido; mesmos valores dos de indicators.py) --

def _rolling_ema(values: list, period: int) -> list:
    if not values:
        return []
    k = 2.0 / (period + 1.0)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1.0 - k))
    return out


def _rolling_rsi(closes: list, period: int) -> list:
    n = len(closes)
    out = [None] * n
    if n < period + 1:
        return out
    gains = losses = 0.0
    for k in range(1, period + 1):
        d = closes[k] - closes[k - 1]
        if d >= 0:
            gains += d
        else:
            losses -= d
    out[period] = 100.0 if losses == 0 else 100.0 - 100.0 / (1.0 + (gains / losses))
    for i in range(period + 1, n):
        d_new = closes[i] - closes[i - 1]
        d_old = closes[i - period] - closes[i - period - 1]
        gains -= d_old if d_old >= 0 else 0.0
        losses -= -d_old if d_old < 0 else 0.0
        gains += d_new if d_new >= 0 else 0.0
        losses += -d_new if d_new < 0 else 0.0
        out[i] = 100.0 if losses == 0 else 100.0 - 100.0 / (1.0 + (gains / losses))
    return out


def _rolling_high(highs: list, lookback: int) -> list:
    """high_window[i] = máxima de highs[i-lookback:i] (janela anterior a i)."""
    n = len(highs)
    out = [0.0] * n
    for i in range(lookback, n):
        out[i] = max(highs[i - lookback:i])
    return out


# ---- simulação pura (testável) ---------------------------------------------

def simulate_symbol(ohlcv: list, p: dict) -> list[dict]:
    """Simula a estratégia num histórico [ts,o,h,l,c,v]. Retorna trades {outcome, roi}.

    Regra: entra quando há dip de p[dip_min..dip_max] a partir da máxima recente,
    RSI saudável e preço acima da EMA. Sai no TP ou SL (SL tem prioridade se ambos
    caírem na mesma vela — pessimista). Indicadores pré-calculados O(N) (rápido).
    """
    if len(ohlcv) < p["lookback"] + 2:
        return []
    highs = [c[2] for c in ohlcv]
    lows = [c[3] for c in ohlcv]
    closes = [c[4] for c in ohlcv]
    bars_24h = p.get("bars_24h", 288)
    rsi_s = _rolling_rsi(closes, p["rsi_period"])
    ema_s = _rolling_ema(closes, p["ema_len"])
    high_s = _rolling_high(highs, p["lookback"])
    trades: list[dict] = []
    open_t = None
    i = p["lookback"]
    n = len(ohlcv)
    while i < n:
        if open_t is None:
            price = closes[i]
            hi = high_s[i]
            dip = (hi - price) / hi if hi > 0 else 0.0
            trend_ok = True
            if bars_24h:
                if i < bars_24h:
                    trend_ok = False
                else:
                    base = closes[i - bars_24h]
                    trend = (price - base) / base if base else 0.0
                    trend_ok = p["min_24h"] <= trend <= p["max_24h"]
            if (trend_ok and p["dip_min"] <= dip <= p["dip_max"]
                    and ta_ok(rsi_s[i], price, ema_s[i], p["rsi_min"], p["rsi_max"])):
                tp, sl = tp_sl_prices(price, p["tp_roi"], p["sl_roi"], p["leverage"])
                open_t = {"tp": tp, "sl": sl}
        else:
            hit = None
            if lows[i] <= open_t["sl"]:
                hit = ("SL", -p["sl_roi"])
            elif highs[i] >= open_t["tp"]:
                hit = ("TP", p["tp_roi"])
            if hit:
                trades.append({"outcome": hit[0], "roi": hit[1] - p["fee_roi"]})
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
    log.info("Backtest | %d símbolos | %d dias | alta 24h %.0f-%.0f%% | dip %.0f-%.0f%% | "
             "TP+%.0f%%/SL-%.0f%% ROI | %dx | taxa %.2f%%",
             len(symbols), days, p["min_24h"] * 100, p["max_24h"] * 100,
             p["dip_min"] * 100, p["dip_max"] * 100,
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


def _fetch_ohlcvs(ex, symbols: list, limit: int) -> list:
    out = []
    for s in symbols:
        try:
            oh = ex.fetch_ohlcv(s, "5m", limit=limit)
            if oh:
                out.append(oh)
        except Exception:  # noqa: BLE001
            continue
    return out


def run_grid(p: dict, top: int, days: int, min_vol: float) -> int:
    """Testa VÁRIAS combinações (TP/SL/dip) de uma vez e ranqueia as melhores."""
    ex = _public_client()
    limit = min(1000, int(days * 24 * 60 / 5))
    symbols = _top_symbols(ex, top, min_vol)
    log.info("Grid | baixando %d moedas (%d dias)... (pode levar ~1-2 min)", len(symbols), days)
    ohlcvs = _fetch_ohlcvs(ex, symbols, limit)
    log.info("Baixado (%d moedas). Testando as combinações...", len(ohlcvs))

    dip_maxes = [0.05, 0.06, 0.08]
    tps = [0.15, 0.20, 0.30]
    sls = [0.10, 0.15]
    combos = [(d, t, s) for d in dip_maxes for t in tps for s in sls]
    results = []
    for idx, (dmax, tp, sl) in enumerate(combos, 1):
        q = dict(p, dip_max=dmax, tp_roi=tp, sl_roi=sl)
        trades = []
        for oh in ohlcvs:
            trades.extend(simulate_symbol(oh, q))
        st = aggregate(trades)
        log.info("  [%d/%d] dip %.0f-%.0f%% TP%.0f/SL%.0f -> %d trades, exp %+.2f%%, PF %.2f",
                 idx, len(combos), p["dip_min"] * 100, dmax * 100, tp * 100, sl * 100,
                 st["count"], st["expectancy"] * 100,
                 st["profit_factor"] if st["profit_factor"] != float("inf") else 99)
        if st["count"] >= 30:
            results.append((dmax, tp, sl, st))
    results.sort(key=lambda r: -r[3]["expectancy"])

    print("=" * 68)
    print("BUSCA EM GRADE (melhores combinações no histórico)")
    print("=" * 68)
    print(f"{'dip':>7} {'TP':>5} {'SL':>5} | {'trades':>6} {'acerto':>6} {'exp/trade':>9} {'PF':>5}")
    print("-" * 68)
    positivos = 0
    for dmax, tp, sl, st in results[:12]:
        pf = "inf" if st["profit_factor"] == float("inf") else f"{st['profit_factor']:.2f}"
        if st["expectancy"] > 0:
            positivos += 1
        print(f"{p['dip_min'] * 100:.0f}-{dmax * 100:.0f}% {tp * 100:>4.0f}% {sl * 100:>4.0f}% | "
              f"{st['count']:>6} {st['win_rate'] * 100:>5.0f}% {st['expectancy'] * 100:>+8.2f}% {pf:>5}")
    print("-" * 68)
    tot = len(results)
    print(f"{sum(1 for r in results if r[3]['expectancy'] > 0)}/{tot} combinações deram POSITIVO.")
    if tot and sum(1 for r in results if r[3]['expectancy'] > 0) / tot >= 0.6:
        print("✅ Maioria positiva — indício de borda ROBUSTA (não é só sorte de uma config).")
    else:
        print("⚠️ Poucas positivas — provável RUÍDO/overfitting. Desconfie do 'melhor'.")
    print("Valide a melhor num período diferente antes de usar (--days maior ou outra época).")
    print("=" * 68)
    return 0


def _params(args) -> dict:
    return {
        "dip_min": args.dip_min, "dip_max": args.dip_max,
        "tp_roi": args.tp, "sl_roi": args.sl, "leverage": args.lev,
        "rsi_period": 14, "rsi_min": args.rsi_min, "rsi_max": args.rsi_max,
        "ema_len": args.ema, "lookback": args.lookback,
        "fee_roi": args.fee,
        "min_24h": args.min_24h, "max_24h": args.max_24h, "bars_24h": 288,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Backtester do Sniper (dados históricos)")
    ap.add_argument("--top", type=int, default=200, help="Nº de perps (por volume) a testar.")
    ap.add_argument("--days", type=int, default=7, help="Dias de histórico (5m).")
    ap.add_argument("--min-vol", type=float, default=2_000_000)
    ap.add_argument("--min-24h", type=float, default=0.15, help="Alta 24h mínima (fiel ao bot).")
    ap.add_argument("--max-24h", type=float, default=0.60, help="Alta 24h máxima.")
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
    ap.add_argument("--grid", action="store_true", help="Testa várias combinações TP/SL/dip e ranqueia.")
    args = ap.parse_args()
    if args.grid:
        return run_grid(_params(args), args.top, args.days, args.min_vol)
    return run_backtest(_params(args), args.top, args.days, args.min_vol)


if __name__ == "__main__":
    import sys
    sys.exit(main())
