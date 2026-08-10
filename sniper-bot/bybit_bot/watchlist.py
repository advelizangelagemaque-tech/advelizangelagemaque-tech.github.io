"""Watchlist com vigia: fica de olho numa lista de moedas e AVISA quando uma
delas vira pra baixo (o detector de rollover acende 🟢).

A ideia: você põe na lista os pumps que quer vigiar (os que hoje dão 🔴 porque
ainda estão subindo). O vigia re-checa de tempos em tempos e, no instante em que
uma finalmente ROLA pra baixo (vira short válido), ele grita o alerta. Assim você
não precisa ficar olhando gráfico o dia todo — espera o aviso. Só leitura, não opera.

Edite a lista em watchlist.txt (uma moeda por linha; 'PEPE' ou 'PEPE/USDT:USDT').
"""

from __future__ import annotations

import argparse
import logging
import os
import time

from .short_setup import detect_short_setup, fetch_candles

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("bybit_bot.watchlist")

DEFAULT_FILE = os.path.join(os.path.dirname(__file__), "..", "watchlist.txt")


# ---- lógica pura (testável) ------------------------------------------------

def normalize_symbol(line: str) -> str | None:
    """'pepe' -> 'PEPE/USDT:USDT'; linha vazia/comentário -> None."""
    s = line.strip().upper()
    if not s or s.startswith("#"):
        return None
    if "/" in s:
        return s
    return f"{s}/USDT:USDT"


def load_watchlist(text: str) -> list[str]:
    """Lê o conteúdo do arquivo em símbolos, sem repetir, mantendo a ordem."""
    out, seen = [], set()
    for line in text.splitlines():
        sym = normalize_symbol(line)
        if sym and sym not in seen:
            seen.add(sym)
            out.append(sym)
    return out


def new_signals(prev_short: set, current_short: set) -> list[str]:
    """Moedas que ACABARAM de virar short (estavam fora, agora estão dentro)."""
    return sorted(current_short - prev_short)


# ---- coleta + vigia (I/O) --------------------------------------------------

def scan(symbols: list[str], tf: str = "4h") -> list[dict]:
    results = []
    for sym in symbols:
        try:
            candles = fetch_candles(sym, tf)
            if len(candles) < 30:
                results.append({"symbol": sym, "light": "erro", "verdict": "pouco histórico"})
                continue
            d = detect_short_setup(candles)
            d["symbol"] = sym
            results.append(d)
        except Exception as exc:  # noqa: BLE001
            results.append({"symbol": sym, "light": "erro", "verdict": str(exc)[:40]})
    return results


def _print_report(results: list[dict], tf: str) -> None:
    icon = {"short": "🟢", "wait": "🔴", "none": "⚪", "erro": "⚠️"}
    print("=" * 60)
    print(f"WATCHLIST ({tf}) — {len(results)} moedas")
    print("=" * 60)
    for r in sorted(results, key=lambda x: {"short": 0, "wait": 1, "none": 2, "erro": 3}[x["light"]]):
        base = r["symbol"].split("/")[0]
        if r["light"] == "short":
            print(f"  🟢 {base:<10} VIROU! short válido — stop acima de {r['recent_high']:.6g}")
        elif r["light"] == "wait":
            print(f"  🔴 {base:<10} ainda de pé (esticado, sem virar)")
        elif r["light"] == "none":
            print(f"  ⚪ {base:<10} sem setup (não esticou)")
        else:
            print(f"  ⚠️ {base:<10} {r['verdict']}")
    print("=" * 60)


def run(symbols: list[str], tf: str, watch: int) -> int:
    if not symbols:
        log.error("Watchlist vazia. Edite watchlist.txt ou passe moedas na linha de comando.")
        return 1
    prev_short: set = set()
    first = True
    while True:
        results = scan(symbols, tf)
        short_now = {r["symbol"] for r in results if r["light"] == "short"}
        fired = new_signals(prev_short, short_now)
        _print_report(results, tf)
        if fired and not first:
            print("\n" + "🔔" * 20)
            for sym in fired:
                print(f"🔔 ALERTA: {sym.split('/')[0]} ACABOU DE VIRAR — short válido agora!")
            print("🔔" * 20 + "\n")
        prev_short = short_now
        first = False
        if watch <= 0:
            return 0
        log.warning("Próxima checagem em %d min... (Ctrl+C pra parar)", watch // 60)
        time.sleep(watch)


def main() -> int:
    p = argparse.ArgumentParser(description="Watchlist com vigia de rollover (só leitura).")
    p.add_argument("symbols", nargs="*", help="Moedas (ex: SQD BSP). Sem isso, usa watchlist.txt.")
    p.add_argument("--file", default=DEFAULT_FILE, help="Arquivo da watchlist.")
    p.add_argument("--tf", default="4h", help="Timeframe (padrão 4h).")
    p.add_argument("--watch", type=int, default=0,
                   help="Vigiar em loop a cada N segundos (ex: 900 = 15 min). 0 = checa uma vez.")
    args = p.parse_args()
    if args.symbols:
        symbols = load_watchlist("\n".join(args.symbols))
    else:
        try:
            with open(args.file, encoding="utf-8") as f:
                symbols = load_watchlist(f.read())
        except FileNotFoundError:
            log.error("Não achei %s. Crie o arquivo ou passe moedas na linha de comando.", args.file)
            return 1
    return run(symbols, args.tf, args.watch)


if __name__ == "__main__":
    import sys
    sys.exit(main())
