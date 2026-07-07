"""Backtest do Delta v2: long/short NEUTRO em moedas LÍQUIDAS, segurando por dias.

A lição das telas da Empiricus: (1) só moedas grandes/líquidas — nada de micro-cap
que explode; (2) segurar por dias/semana — nada de churn de 24h. Aqui a gente
mede isso em ~6 meses de histórico, ANTES de arriscar. Testa momentum (compra
fortes, vende fracos) E reversão (o contrário) pra ver o que funcionou.

A matemática é pura e testável; a coleta usa ccxt (só leitura).
"""

from __future__ import annotations

import argparse
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("bybit_bot.delta_backtest")

# Universo curado de perps USDT LÍQUIDOS e estabelecidos (têm meses de histórico).
LIQUID_UNIVERSE = [
    "BTC", "ETH", "SOL", "XRP", "BNB", "DOGE", "ADA", "AVAX", "LINK", "DOT",
    "LTC", "BCH", "TRX", "UNI", "ATOM", "NEAR", "APT", "ARB", "OP", "INJ",
    "SUI", "FIL", "AAVE", "LDO", "TIA", "SEI", "RUNE", "ALGO", "IMX", "RENDER",
]


# ---- matemática pura (testável) --------------------------------------------

def rank_longs_shorts(scores: dict, k: int) -> tuple[list[str], list[str]]:
    """Top-k por score = LONG; bottom-k = SHORT. Sem sobreposição."""
    s = sorted(scores, key=lambda x: -scores[x])
    if len(s) < 2 * k:
        k = len(s) // 2
    if k <= 0:
        return [], []
    return s[:k], s[-k:]


def path_return(closes: list, t0: int, t1: int, side: int, stop: float) -> float:
    """Retorno de UMA posição de t0 a t1 (side +1 long / -1 short), com stop.
    Se o prejuízo passar de `stop` em algum dia do caminho, sai no stop."""
    entry = closes[t0]
    if entry <= 0:
        return 0.0
    if stop > 0:
        for d in range(t0 + 1, t1 + 1):
            r = (closes[d] / entry - 1) * side
            if r <= -stop:
                return -stop
    return (closes[t1] / entry - 1) * side


def simulate_delta(prices: dict, lookback: int = 14, hold: int = 7, k: int = 5,
                   stop: float = 0.25, fee_bps: float = 5.0, direction: int = 1) -> dict:
    """Simula o Delta long/short. direction=+1 momentum (compra fortes / vende
    fracos); -1 reversão (o contrário). Devolve curva de capital e métricas."""
    symbols = list(prices)
    if not symbols:
        return {"final": 1.0, "curve": [1.0], "periods": [], "rebalances": 0}
    n = len(prices[symbols[0]])
    equity = 1.0
    curve = [1.0]
    periods = []
    t = lookback
    while t + 1 < n:
        scores = {}
        for s in symbols:
            p0, p1 = prices[s][t - lookback], prices[s][t]
            if p0 > 0:
                scores[s] = (p1 / p0 - 1) * direction
        longs, shorts = rank_longs_shorts(scores, k)
        kk = len(longs)
        if kk == 0:
            break
        h = min(hold, n - 1 - t)
        size = 1.0 / (2 * kk)                       # peso igual, metade long metade short
        pnl = 0.0
        for s in longs:
            pnl += size * path_return(prices[s], t, t + h, +1, stop)
        for s in shorts:
            pnl += size * path_return(prices[s], t, t + h, -1, stop)
        fee = 2 * (fee_bps / 10_000.0)              # gira o livro (entra+sai) a cada rebalance
        ret = pnl - fee
        equity *= (1 + ret)
        periods.append(ret)
        curve.append(equity)
        t += h
    return {"final": equity, "curve": curve, "periods": periods, "rebalances": len(periods)}


def metrics(sim: dict) -> dict:
    """Métricas honestas da simulação."""
    curve = sim["curve"]
    periods = sim["periods"]
    total = sim["final"] - 1
    peak = curve[0]
    max_dd = 0.0
    for v in curve:
        peak = max(peak, v)
        max_dd = max(max_dd, (peak - v) / peak if peak > 0 else 0.0)
    wins = sum(1 for r in periods if r > 0)
    win_rate = wins / len(periods) if periods else 0.0
    best = max(periods) if periods else 0.0
    worst = min(periods) if periods else 0.0
    return {"total_return": total, "max_drawdown": max_dd, "win_rate": win_rate,
            "best": best, "worst": worst, "rebalances": sim["rebalances"]}


# ---- coleta (rede pública, só leitura) -------------------------------------

def fetch_prices(symbols: list, days: int = 180) -> dict:
    """Fecha diário dos últimos `days` dias, alinhado por data. {symbol: [closes]}."""
    try:
        import ccxt
    except ImportError:
        raise SystemExit("ccxt não está instalado. Rode:  pip install ccxt")
    ex = ccxt.bybit({"enableRateLimit": True, "options": {"defaultType": "swap"}})
    by_ts: dict = {}
    for base in symbols:
        sym = f"{base}/USDT:USDT"
        try:
            ohlcv = ex.fetch_ohlcv(sym, "1d", limit=days)
        except Exception as exc:  # noqa: BLE001
            log.warning("Pulei %s (%s)", base, str(exc)[:50])
            continue
        if len(ohlcv) < days * 0.7:                 # pouco histórico -> fora
            continue
        by_ts[base] = {c[0]: c[4] for c in ohlcv}
    if not by_ts:
        return {}
    common = set.intersection(*(set(v) for v in by_ts.values()))
    ts_sorted = sorted(common)
    return {b: [by_ts[b][t] for t in ts_sorted] for b in by_ts}


def run_backtest(days: int, lookback: int, hold: int, k: int, stop: float, fee_bps: float) -> int:
    log.warning("Baixando ~%d dias de %d moedas líquidas...", days, len(LIQUID_UNIVERSE))
    prices = fetch_prices(LIQUID_UNIVERSE, days)
    if not prices:
        log.error("Sem dados. Verifique a conexão/ccxt.")
        return 1
    ndays = len(next(iter(prices.values())))
    months = ndays / 30.0
    print("=" * 66)
    print(f"BACKTEST DELTA v2 | {len(prices)} moedas líquidas | {ndays} dias (~{months:.1f} meses)")
    print(f"Config: momentum de {lookback}d | segura {hold}d | {k}+{k} posições | "
          f"stop {stop*100:.0f}% | taxa {fee_bps/100:.2f}%/rebal")
    print("=" * 66)
    for name, direction in [("MOMENTUM (compra fortes / vende fracos)", 1),
                            ("REVERSÃO (compra fracos / vende fortes)", -1)]:
        sim = simulate_delta(prices, lookback, hold, k, stop, fee_bps, direction)
        m = metrics(sim)
        mensal = (1 + m["total_return"]) ** (1 / months) - 1 if months > 0 else 0.0
        marca = "✅" if m["total_return"] > 0 else "❌"
        print(f"\n{marca} {name}")
        print(f"    Retorno total : {m['total_return']*100:+.1f}%   (~{mensal*100:+.1f}%/mês)")
        print(f"    Pior queda    : -{m['max_drawdown']*100:.1f}%  (drawdown máximo)")
        print(f"    Acertos       : {m['win_rate']*100:.0f}% dos {m['rebalances']} rebalances")
        print(f"    Melhor/pior rebal: {m['best']*100:+.1f}% / {m['worst']*100:+.1f}%")
    print("\n" + "=" * 66)
    print("Honestidade: passado NÃO garante futuro; usa fecho diário (o stop é")
    print("aproximado); e assume giro do livro todo rebalance (taxa conservadora).")
    print("=" * 66)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Backtest do Delta v2 (long/short em moedas líquidas).")
    p.add_argument("--days", type=int, default=180, help="Dias de histórico (padrão 180 = ~6 meses).")
    p.add_argument("--lookback", type=int, default=14, help="Janela do momentum, em dias.")
    p.add_argument("--hold", type=int, default=7, help="Dias segurando cada cesta (rebalance).")
    p.add_argument("--k", type=int, default=5, help="Posições por lado (long e short).")
    p.add_argument("--stop", type=float, default=0.25, help="Stop por posição (0.25 = -25%%).")
    p.add_argument("--fee-bps", type=float, default=5.0, help="Taxa por rebalance em pontos-base.")
    args = p.parse_args()
    return run_backtest(args.days, args.lookback, args.hold, args.k, args.stop, args.fee_bps)


if __name__ == "__main__":
    import sys
    sys.exit(main())
