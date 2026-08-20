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
from .telegram_alert import get_config, send_message

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


def new_signals(prev_short: set, current_short: set,
                last_alert: dict | None = None, now: float = 0.0,
                cooldown: float = 0.0) -> list[str]:
    """Moedas que ACABARAM de virar short (estavam fora, agora entraram).

    Com o cooldown ligado (cooldown>0 e last_alert dado), NÃO repete o alerta da
    mesma moeda dentro de `cooldown` segundos. Isso mata o spam de quando a moeda
    fica piscando 🟢/🔴 em cima da linha e re-dispara o mesmo aviso toda hora."""
    out = []
    for s in sorted(current_short - prev_short):
        if last_alert is not None and cooldown > 0:
            if now - last_alert.get(s, float("-inf")) < cooldown:
                continue          # já avisei essa faz pouco tempo — segura o spam
        out.append(s)
    return out


def refresh_symbols(results: list[dict], gainer_symbols: list[str]) -> list[str]:
    """Nova watchlist: mantém os candidatos ATIVOS (🟢 short / 🔴 ainda de pé) e
    adiciona os top gainers de agora; corta os FRIOS (⚪ sem setup) que já
    esfriaram e não estão mais em alta. Assim a lista fica fresca e não incha."""
    keep = [r["symbol"] for r in results if r.get("light") in ("short", "wait")]
    out, seen = [], set()
    for s in keep + list(gainer_symbols):
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def watchlist_text(symbols: list[str]) -> str:
    """Serializa a watchlist pro arquivo (só os tickers, um por linha)."""
    header = ("# Watchlist do vigia (atualizada automaticamente pelo --auto-refresh).\n"
              "# Uma moeda por linha. # ignora a linha.\n\n")
    return header + "\n".join(s.split("/")[0] for s in symbols) + "\n"


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


def _telegram_notify(fired: list[str], results: list[dict]) -> None:
    """Manda o alerta pro Telegram, se estiver configurado. Silencioso se não."""
    token, chat = get_config()
    if not token or not chat:
        log.warning("Telegram sem config (.env.telegram) — alerta só na tela.")
        return
    by_sym = {r["symbol"]: r for r in results}
    for sym in fired:
        r = by_sym.get(sym, {})
        stop = r.get("recent_high")
        dist = r.get("dist_stop_pct")
        price = r.get("price")
        base = sym.split("/")[0]
        if stop and dist is not None:
            largura = "stop LARGO, valor menor" if dist >= 20 else "stop ok"
            msg = (f"🔔 {base} ACABOU DE VIRAR — short válido agora!\n"
                   f"Preço ~{price:.6g} · Stop acima de {stop:.6g} (+{dist:.1f}% daqui).\n"
                   f"Valor pequeno, 2x. ({largura})")
        else:
            msg = f"🔔 {base} ACABOU DE VIRAR — short válido agora!"
        try:
            send_message(token, chat, msg)
        except Exception as exc:  # noqa: BLE001
            log.warning("Falha ao enviar Telegram: %s", str(exc)[:60])


def _auto_refresh(symbols: list[str], results: list[dict], file: str,
                  n: int, min_vol: float) -> list[str]:
    """Busca os top gainers e reconstrói a lista (candidatos ativos + em alta),
    grava no arquivo e devolve a nova lista. Silencioso em erro (mantém a atual)."""
    try:
        from .top_gainers import fetch_tickers, top_gainers
        tickers = fetch_tickers()
        gainers = [g["symbol"] for g in top_gainers(tickers, n, min_vol)]
        new = refresh_symbols(results, gainers)
        if not new:
            return symbols
        with open(file, "w", encoding="utf-8") as f:
            f.write(watchlist_text(new))
        add = [s.split("/")[0] for s in new if s not in symbols]
        rm = [s.split("/")[0] for s in symbols if s not in new]
        log.warning("Lista atualizada: %d moedas (+%s / -%s)", len(new),
                    ",".join(add) or "0", ",".join(rm) or "0")
        return new
    except Exception as exc:  # noqa: BLE001
        log.warning("Falha ao atualizar a lista: %s", str(exc)[:60])
        return symbols


def run(symbols: list[str], tf: str, watch: int, telegram: bool = False,
        file: str = DEFAULT_FILE, auto_refresh_min: int = 0,
        top_n: int = 5, min_vol: float = 30_000_000, cooldown_min: int = 360) -> int:
    if not symbols:
        log.error("Watchlist vazia. Edite watchlist.txt ou passe moedas na linha de comando.")
        return 1
    refresh_every = max(1, round(auto_refresh_min * 60 / watch)) if (auto_refresh_min and watch) else 0
    cooldown_sec = max(0, cooldown_min) * 60
    prev_short: set = set()
    last_alert: dict[str, float] = {}     # moeda -> quando avisei por último (anti-spam)
    first = True
    cycle = 0
    while True:
        now = time.time()
        results = scan(symbols, tf)
        short_now = {r["symbol"] for r in results if r["light"] == "short"}
        fired = new_signals(prev_short, short_now, last_alert, now, cooldown_sec)
        _print_report(results, tf)
        if fired and not first:
            for sym in fired:
                last_alert[sym] = now      # marca pra não repetir dentro do cooldown
            print("\n" + "🔔" * 20)
            for sym in fired:
                print(f"🔔 ALERTA: {sym.split('/')[0]} ACABOU DE VIRAR — short válido agora!")
            print("🔔" * 20 + "\n")
            if telegram:
                _telegram_notify(fired, results)
        prev_short = short_now
        first = False
        if watch <= 0:
            return 0
        cycle += 1
        if refresh_every and cycle % refresh_every == 0:
            symbols = _auto_refresh(symbols, results, file, top_n, min_vol)
        log.warning("Próxima checagem em %d min... (Ctrl+C pra parar)", watch // 60)
        time.sleep(watch)


def main() -> int:
    p = argparse.ArgumentParser(description="Watchlist com vigia de rollover (só leitura).")
    p.add_argument("symbols", nargs="*", help="Moedas (ex: SQD BSP). Sem isso, usa watchlist.txt.")
    p.add_argument("--file", default=DEFAULT_FILE, help="Arquivo da watchlist.")
    p.add_argument("--tf", default="4h", help="Timeframe (padrão 4h).")
    p.add_argument("--watch", type=int, default=0,
                   help="Vigiar em loop a cada N segundos (ex: 900 = 15 min). 0 = checa uma vez.")
    p.add_argument("--telegram", action="store_true",
                   help="Manda o alerta pro Telegram (precisa do .env.telegram na EC2).")
    p.add_argument("--auto-refresh", type=int, default=0, metavar="MIN",
                   help="Atualiza a lista com os top gainers a cada MIN minutos (ex: 60). 0 = off.")
    p.add_argument("--top-n", type=int, default=5, help="Quantos top gainers puxar no refresh.")
    p.add_argument("--cooldown-min", type=int, default=360, metavar="MIN",
                   help="Não repete o alerta da mesma moeda por MIN minutos (padrão 360 = 6h). 0 = sem cooldown.")
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
    return run(symbols, args.tf, args.watch, args.telegram,
               file=args.file, auto_refresh_min=args.auto_refresh, top_n=args.top_n,
               cooldown_min=args.cooldown_min)


if __name__ == "__main__":
    import sys
    sys.exit(main())
