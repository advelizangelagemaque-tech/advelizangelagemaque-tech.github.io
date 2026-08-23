"""Radar de PUMP FRESCO: acha as moedas que estão subindo forte AGORA, ainda
quentes (perto do topo) e com volume acima do normal — cedo, antes de rolarem.

A ideia NÃO é comprar o foguete (isso é loteria). É o contrário: achar o pump
cedo e já jogar na watchlist, pra o VIGIA avisar quando ela ROLAR pra baixo —
que é onde a gente ganha de verdade (short 2x, 92% no diário). O radar é o
garimpo que ALIMENTA a estratégia campeã. Só leitura, não opera.

Uso:
  python -m bybit_bot.pump_radar                 # mostra os pumps frescos
  python -m bybit_bot.pump_radar --add           # e já joga na watchlist do vigia
"""

from __future__ import annotations

import argparse
import logging
import os

from .entry_check import rsi
from .short_setup import fetch_candles

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("bybit_bot.pump_radar")

WATCHLIST_PATH = os.path.join(os.path.dirname(__file__), "..", "watchlist.txt")


# ---- lógica pura (testável) ------------------------------------------------

def detect_pump(candles: list, window: int = 12, pump_min: float = 0.20,
                vol_min: float = 1.5, fade_max: float = 0.12) -> dict:
    """Classifica quão 'pump fresco' está a moeda, a partir das velas.

    🔥 fire  = subiu forte na janela (pumped), ainda perto do topo (hot) e com
               volume acima do normal (volume). É o candidato pra vigiar.
    🟠 warm  = subindo, mas falta uma das três — de olho.
    ⚪ none  = sem pump.

    Fresco = perto do topo (near_high): a gente quer pegar ANTES de rolar, não
    depois que já caiu. O short vem depois, quando o vigia vê a virada.
    """
    if len(candles) < window + 5:
        return {"light": "none", "verdict": "pouco histórico", "run_pct": 0.0,
                "vol_ratio": 0.0, "pumped": False, "hot": False, "volume": False}
    closes = [c[4] for c in candles]
    highs = [c[2] for c in candles]
    vols = [c[5] for c in candles]

    base = closes[-window]
    price = closes[-1]
    run_pct = (price - base) / base if base > 0 else 0.0
    recent_high = max(highs[-window:])
    near_high = recent_high > 0 and price >= recent_high * (1 - fade_max)

    recent_vol = sum(vols[-3:]) / 3
    base_vol = sum(vols[-window - 3:-3]) / window
    vol_ratio = (recent_vol / base_vol) if base_vol > 0 else 0.0

    r = rsi(closes, 14)
    r = r if r is not None else 50.0

    pumped = run_pct >= pump_min
    hot = near_high
    volume = vol_ratio >= vol_min

    if pumped and hot and volume:
        light = "fire"
        verdict = "PUMP FRESCO 🔥 — pôr na watchlist e esperar ROLAR pra shortar"
    elif pumped and (hot or volume):
        light = "warm"
        verdict = "esquentando — de olho"
    else:
        light = "none"
        verdict = "sem pump"

    return {
        "light": light, "verdict": verdict,
        "run_pct": run_pct, "vol_ratio": vol_ratio, "rsi": r,
        "price": price, "recent_high": recent_high,
        "pumped": pumped, "hot": hot, "volume": volume,
    }


def pick_fires(results: list[dict]) -> list[str]:
    """Símbolos que estão em PUMP FRESCO (🔥), do mais forte pro mais fraco."""
    fires = [r for r in results if r.get("light") == "fire"]
    fires.sort(key=lambda r: -r.get("run_pct", 0.0))
    return [r["symbol"] for r in fires]


# ---- coleta + varredura (rede pública, só leitura) -------------------------

def radar_scan(symbols: list[str], tf: str = "1h") -> list[dict]:
    results = []
    for sym in symbols:
        try:
            candles = fetch_candles(sym, tf)
            d = detect_pump(candles)
            d["symbol"] = sym
            results.append(d)
        except Exception as exc:  # noqa: BLE001
            results.append({"symbol": sym, "light": "erro", "verdict": str(exc)[:40],
                            "run_pct": 0.0})
    return results


def _candidate_symbols(top_n: int, min_vol: float) -> list[str]:
    """Pré-filtro barato: pega os maiores movimentos de 24h (líquidos) como
    pool de candidatos, pra não puxar velas do mercado inteiro."""
    from .top_gainers import fetch_tickers, top_gainers
    tickers = fetch_tickers()
    return [g["symbol"] for g in top_gainers(tickers, top_n, min_vol)]


def _print_report(results: list[dict], tf: str) -> None:
    order = {"fire": 0, "warm": 1, "none": 2, "erro": 3}
    icon = {"fire": "🔥", "warm": "🟠", "none": "⚪", "erro": "⚠️"}
    print("=" * 64)
    print(f"RADAR DE PUMP FRESCO ({tf}) — {len(results)} moedas varridas")
    print("=" * 64)
    for r in sorted(results, key=lambda x: (order.get(x["light"], 9), -x.get("run_pct", 0.0))):
        base = r["symbol"].split("/")[0]
        if r["light"] == "fire":
            print(f"  🔥 {base:<10} +{r['run_pct']*100:.0f}% na janela · vol {r['vol_ratio']:.1f}x "
                  f"· RSI {r['rsi']:.0f}  → vigiar pra shortar quando rolar")
        elif r["light"] == "warm":
            print(f"  🟠 {base:<10} +{r['run_pct']*100:.0f}% · vol {r.get('vol_ratio',0):.1f}x  (esquentando)")
        elif r["light"] == "erro":
            print(f"  ⚠️ {base:<10} {r['verdict']}")
    print("=" * 64)


def run(tf: str, top_n: int, min_vol: float, add: bool) -> int:
    log.warning("Garimpando pumps frescos na Bybit...")
    try:
        symbols = _candidate_symbols(top_n, min_vol)
    except Exception as exc:  # noqa: BLE001
        log.error("Falha ao buscar candidatos: %s", str(exc)[:80])
        return 1
    if not symbols:
        log.error("Nenhum candidato (sem movimento/liquidez). Tente baixar --min-vol.")
        return 1
    results = radar_scan(symbols, tf)
    _print_report(results, tf)

    fires = pick_fires(results)
    if not fires:
        print("Nenhum pump fresco 🔥 agora. O radar segue de olho — rode de novo mais tarde.")
        return 0
    print(f"🔥 {len(fires)} pump(s) fresco(s): {', '.join(s.split('/')[0] for s in fires)}")
    if add:
        from .top_gainers import merge_into_watchlist
        try:
            with open(WATCHLIST_PATH, encoding="utf-8") as f:
                text = f.read()
        except FileNotFoundError:
            text = ""
        with open(WATCHLIST_PATH, "w", encoding="utf-8") as f:
            f.write(merge_into_watchlist(text, fires))
        print("✅ Adicionados na watchlist.txt — o vigia vai avisar quando ROLAREM.")
        print("   Reinicie o vigia:  sudo systemctl restart watchlist-vigia")
    else:
        print("Pra jogar na watchlist do vigia, rode de novo com --add")
    print("=" * 64)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Radar de pump fresco (alimenta o short). Só leitura.")
    p.add_argument("--tf", default="1h", help="Timeframe pra detectar o pump (padrão 1h = pega cedo).")
    p.add_argument("--top-n", type=int, default=30, help="Quantos movers de 24h varrer (padrão 30).")
    p.add_argument("--min-vol", type=float, default=20_000_000, help="Volume 24h mínimo (USDT).")
    p.add_argument("--add", action="store_true", help="Joga os 🔥 na watchlist.txt do vigia.")
    args = p.parse_args()
    return run(args.tf, args.top_n, args.min_vol, args.add)


if __name__ == "__main__":
    import sys
    sys.exit(main())
