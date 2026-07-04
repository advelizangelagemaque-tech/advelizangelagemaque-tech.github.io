"""Sniper de LANÇAMENTOS Bybit (perps) — detector/observador (etapa 1) + execução (etapa 2).

Etapa 1 (sem dinheiro): detecta quando um novo perp USDT é listado e REGISTRA como
ele se comporta nas primeiras horas (retorno em 1, 5, 15, 30, 60, 120 min). Isso
gera o dado pra a gente descobrir SE existe borda (pumpa e cai? compensa comprar,
shortar, ou esperar o pullback?).

Etapa 2 (com dinheiro, opcional --live): ao detectar um lançamento, entra numa
posição conforme a regra configurada (lado, atraso, TP/SL). Só arme depois de
olhar os dados da etapa 1.

    python -m bybit_bot.launch                 # observa (sem ordens)
    python -m bybit_bot.launch --report        # resumo dos lançamentos observados
    python -m bybit_bot.launch --live          # ARMA o sniper (etapa 2) — exige chaves
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("bybit_bot.launch")

KNOWN_PATH = "launch_known.json"
OBS_PATH = "launch_obs.csv"
WATCH_PATH = "launch_watch.json"
CHECKPOINTS = [1, 5, 15, 30, 60, 120]     # minutos observados
OBS_WINDOW_MIN = 120                        # observa cada lançamento por 2h
_OBS_FIELDS = ["symbol", "first_price", "elapsed_min", "price", "ret_pct"]


# ---- lógica pura (testável) ------------------------------------------------

def perp_symbols(tickers: dict) -> set:
    """Símbolos de perp USDT presentes agora."""
    return {s for s in tickers if s.endswith(":USDT")}


def detect_new(current: set, known: set) -> list:
    """Símbolos que existem agora e não existiam antes (novas listagens)."""
    return sorted(set(current) - set(known))


def ret_pct(first_price: float, price: float) -> float:
    """Retorno percentual (fração) desde o preço de listagem."""
    if not first_price:
        return 0.0
    return (price - first_price) / first_price


def nearest_ret(rows: list, checkpoint: int, tol: float = 3.0):
    """Retorno da observação mais próxima do checkpoint (min). None se não houver."""
    best = None
    best_d = None
    for r in rows:
        d = abs(float(r["elapsed_min"]) - checkpoint)
        if d <= tol and (best_d is None or d < best_d):
            best, best_d = r, d
    return float(best["ret_pct"]) if best else None


def summarize(rows: list, checkpoints=CHECKPOINTS) -> dict:
    """Agrega os retornos por checkpoint: média e % de casos positivos."""
    by_sym: dict[str, list] = {}
    for r in rows:
        by_sym.setdefault(r["symbol"], []).append(r)
    out = {}
    for cp in checkpoints:
        rets = []
        for _, srows in by_sym.items():
            v = nearest_ret(srows, cp)
            if v is not None:
                rets.append(v)
        if rets:
            up = sum(1 for v in rets if v > 0)
            out[cp] = {"n": len(rets), "media": sum(rets) / len(rets),
                       "pct_up": up / len(rets)}
    return out, len(by_sym)


# ---- persistência ----------------------------------------------------------

def load_known(path: str = KNOWN_PATH) -> set:
    try:
        with open(path, encoding="utf-8") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_known(symbols: set, path: str = KNOWN_PATH) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sorted(symbols), f)


def _load_watch(path: str = WATCH_PATH) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_watch(watch: dict, path: str = WATCH_PATH) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(watch, f)


def record_obs(symbol: str, first_price: float, elapsed_min: float, price: float,
               path: str = OBS_PATH) -> None:
    novo = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_OBS_FIELDS)
        if novo:
            w.writeheader()
        w.writerow({"symbol": symbol, "first_price": f"{first_price:.10f}",
                    "elapsed_min": f"{elapsed_min:.1f}", "price": f"{price:.10f}",
                    "ret_pct": f"{ret_pct(first_price, price):.5f}"})


def load_obs(path: str = OBS_PATH) -> list:
    try:
        with open(path, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except FileNotFoundError:
        return []


# ---- cliente ---------------------------------------------------------------

def _public_client():
    import ccxt
    return ccxt.bybit({"options": {"defaultType": "swap"}, "enableRateLimit": True})


def _last(tickers: dict, sym: str) -> float:
    t = tickers.get(sym) or {}
    try:
        return float(t.get("last") or 0)
    except (TypeError, ValueError):
        return 0.0


# ---- etapa 2: execução (opcional) ------------------------------------------

def load_launch_config() -> dict:
    try:
        from dotenv import load_dotenv
        if os.path.exists(".env.launch"):
            load_dotenv(".env.launch", override=True)
    except ImportError:  # pragma: no cover
        pass
    priv = os.getenv("LAUNCH_API_PRIVATE_KEY_PATH", "").strip()
    secret = os.getenv("LAUNCH_API_SECRET", "")
    if priv and os.path.exists(os.path.expanduser(priv)):
        with open(os.path.expanduser(priv), encoding="utf-8") as f:
            secret = f.read()
    return {
        "api_key": os.getenv("LAUNCH_API_KEY", ""),
        "secret": secret,
        "testnet": os.getenv("LAUNCH_TESTNET", "false").strip().lower() in {"1", "true", "yes", "sim"},
        "side": os.getenv("LAUNCH_SIDE", "short").strip().lower(),   # short = fadar o pump
        "entry_delay_min": float(os.getenv("LAUNCH_ENTRY_DELAY_MIN", "15")),
        "tp": float(os.getenv("LAUNCH_TP", "0.10")),                  # +10% no preço
        "sl": float(os.getenv("LAUNCH_SL", "0.10")),                  # -10% no preço
        "margin": float(os.getenv("LAUNCH_MARGIN", "10")),
        "leverage": int(os.getenv("LAUNCH_LEVERAGE", "2")),
    }


def _make_client(lc: dict):
    import ccxt
    if not lc["api_key"] or not lc["secret"]:
        raise ValueError("Faltam chaves em .env.launch (LAUNCH_API_KEY / LAUNCH_API_PRIVATE_KEY_PATH).")
    ex = ccxt.bybit({"apiKey": lc["api_key"], "secret": lc["secret"],
                     "enableRateLimit": True, "options": {"defaultType": "swap"}})
    if lc["testnet"]:
        ex.set_sandbox_mode(True)
    return ex


def snipe(ex, lc: dict, symbol: str) -> dict:
    """Abre a posição de lançamento (long/short) com TP/SL no preço."""
    from .trader import set_leverage_safe
    set_leverage_safe(ex, lc["leverage"], symbol)
    price = float(ex.fetch_ticker(symbol)["last"])
    qty = float(ex.amount_to_precision(symbol, lc["margin"] * lc["leverage"] / price))
    side = "buy" if lc["side"] == "long" else "sell"
    if lc["side"] == "long":
        tp, sl = price * (1 + lc["tp"]), price * (1 - lc["sl"])
    else:
        tp, sl = price * (1 - lc["tp"]), price * (1 + lc["sl"])
    tp = float(ex.price_to_precision(symbol, tp))
    sl = float(ex.price_to_precision(symbol, sl))
    ex.create_order(symbol, "market", side, qty, None,
                    {"takeProfit": str(tp), "stopLoss": str(sl), "tpslMode": "Full"})
    return {"symbol": symbol, "side": lc["side"], "entry": price, "tp": tp, "sl": sl}


# ---- loop observador (+ sniper opcional) -----------------------------------

def run(poll_sec: float, live: bool) -> int:
    ex = _public_client()
    lc = load_launch_config() if live else None
    client = _make_client(lc) if live else None
    known = load_known()
    watch = _load_watch()
    log.warning("Sniper de lançamentos | %s | vigiando novos perps USDT...",
                "LIVE (ARMADO)" if live else "OBSERVANDO (sem ordens)")
    if live:
        log.warning("Regra: %s | entra %.0f min após listar | TP %.0f%% / SL %.0f%% | %dx",
                    lc["side"].upper(), lc["entry_delay_min"], lc["tp"] * 100,
                    lc["sl"] * 100, lc["leverage"])

    while True:
        try:
            try:
                ex.load_markets(True)     # recarrega p/ enxergar símbolos novos
            except Exception:  # noqa: BLE001
                pass
            tickers = ex.fetch_tickers()
            current = perp_symbols(tickers)
            now = time.time()

            if not known:                 # 1ª execução: semeia, não dispara nada
                save_known(current)
                known = current
                log.warning("Semente: %d perps conhecidos. A partir de agora, só os NOVOS "
                            "são lançamentos.", len(current))
            else:
                for s in detect_new(current, known):
                    price = _last(tickers, s)
                    watch[s] = {"first_ts": now, "first_price": price, "entered": False}
                    record_obs(s, price, 0.0, price)
                    log.warning("🚀 NOVA LISTAGEM: %s @ %.8f", s, price)
                    known.add(s)
                save_known(known)

            for s in list(watch):
                info = watch[s]
                elapsed = (now - info["first_ts"]) / 60.0
                price = _last(tickers, s)
                if price > 0:
                    record_obs(s, info["first_price"], elapsed, price)
                # etapa 2: entra na hora certa, se armado
                if live and not info["entered"] and elapsed >= lc["entry_delay_min"]:
                    try:
                        res = snipe(client, lc, s)
                        info["entered"] = True
                        log.warning("SNIPE %s %s | entry~%.8f TP=%.8f SL=%.8f",
                                    res["side"].upper(), s, res["entry"], res["tp"], res["sl"])
                    except Exception as exc:  # noqa: BLE001
                        log.error("Falha no snipe de %s: %s", s, exc)
                        info["entered"] = True   # não fica tentando pra sempre
                if elapsed >= OBS_WINDOW_MIN:
                    del watch[s]
            _save_watch(watch)
        except Exception as exc:  # noqa: BLE001
            log.error("Erro no loop (segue): %s", exc)
        time.sleep(poll_sec)


def report() -> int:
    rows = load_obs()
    if not rows:
        log.warning("Ainda não há lançamentos observados. Deixe o observador rodar.")
        return 0
    resumo, n_sym = summarize(rows)
    print("=" * 56)
    print(f"LANÇAMENTOS OBSERVADOS: {n_sym}")
    print("=" * 56)
    print(f"{'minuto':>7} | {'nº':>3} | {'retorno médio':>14} | {'% que subiu':>11}")
    print("-" * 56)
    for cp in CHECKPOINTS:
        if cp in resumo:
            r = resumo[cp]
            print(f"{cp:>6}m | {r['n']:>3} | {r['media'] * 100:>+12.1f}% | {r['pct_up'] * 100:>9.0f}%")
    print("=" * 56)
    print("Leitura: retorno médio POSITIVO = comprar tende a valer; NEGATIVO = fadar (short).")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Sniper de lançamentos Bybit")
    p.add_argument("--report", action="store_true", help="Mostra o resumo dos lançamentos observados.")
    p.add_argument("--live", action="store_true", help="ARMA o sniper (etapa 2) — envia ordens.")
    p.add_argument("--poll", type=float, default=45.0, help="Segundos entre verificações.")
    args = p.parse_args()
    if args.report:
        return report()
    return run(args.poll, args.live)


if __name__ == "__main__":
    import sys
    sys.exit(main())
