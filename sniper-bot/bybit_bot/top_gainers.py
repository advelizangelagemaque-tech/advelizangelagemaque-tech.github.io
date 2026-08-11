"""Pega os tokens EM ALTA agora na Bybit (perps USDT líquidos) e, se quiser,
já adiciona na watchlist do vigia. Só leitura, não opera.

Serve pra alimentar o vigia de rollover: os que estão bombando hoje são os
candidatos a shortar QUANDO virarem. A gente pega os top-N de alta 24h, filtra
liquidez (nada de moeda fina), e opcionalmente escreve na watchlist.txt.
"""

from __future__ import annotations

import argparse
import logging
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("bybit_bot.top_gainers")

WATCHLIST_PATH = os.path.join(os.path.dirname(__file__), "..", "watchlist.txt")


# ---- lógica pura (testável) ------------------------------------------------

def top_gainers(tickers: dict, n: int = 5, min_vol_usdt: float = 30_000_000) -> list[dict]:
    """Top-n perps USDT por alta 24h, só os líquidos. [{symbol, pct, vol}]."""
    rows = []
    for sym, t in tickers.items():
        if not sym.endswith(":USDT"):
            continue
        vol = t.get("quoteVolume") or t.get("baseVolume")
        pct = t.get("percentage")
        if vol is None or pct is None or float(vol) < min_vol_usdt:
            continue
        rows.append({"symbol": sym, "pct": float(pct), "vol": float(vol)})
    rows.sort(key=lambda r: -r["pct"])
    return rows[:n]


def merge_into_watchlist(existing_text: str, symbols: list[str]) -> str:
    """Acrescenta os tickers novos ao conteúdo da watchlist, sem repetir."""
    present = set()
    for line in existing_text.splitlines():
        s = line.strip().upper()
        if s and not s.startswith("#"):
            present.add(s.split("/")[0])            # guarda só o ticker base
    novos = []
    for sym in symbols:
        base = sym.split("/")[0].upper()
        if base not in present:
            present.add(base)
            novos.append(base)
    if not novos:
        return existing_text
    sep = "" if existing_text.endswith("\n") or not existing_text else "\n"
    return existing_text + sep + "\n".join(novos) + "\n"


# ---- coleta (rede pública, só leitura) -------------------------------------

def fetch_tickers() -> dict:
    try:
        import ccxt
    except ImportError:
        raise SystemExit("ccxt não está instalado. Rode:  pip3 install ccxt")
    ex = ccxt.bybit({"enableRateLimit": True, "options": {"defaultType": "swap"}})
    return ex.fetch_tickers()


def run(n: int, min_vol: float, add: bool) -> int:
    log.warning("Buscando as moedas em alta na Bybit...")
    tickers = fetch_tickers()
    top = top_gainers(tickers, n, min_vol)
    if not top:
        log.error("Nada retornado. Verifique a conexão/ccxt.")
        return 1
    print("=" * 60)
    print(f"TOP {len(top)} EM ALTA agora (perps USDT, vol > ${min_vol/1e6:.0f}M)")
    print("=" * 60)
    for i, r in enumerate(top, 1):
        base = r["symbol"].split("/")[0]
        print(f"  {i}. {base:<10} {r['pct']:+.1f}%   (vol ${r['vol']/1e6:.0f}M)")
    print("=" * 60)
    if add:
        try:
            with open(WATCHLIST_PATH, encoding="utf-8") as f:
                text = f.read()
        except FileNotFoundError:
            text = ""
        new_text = merge_into_watchlist(text, [r["symbol"] for r in top])
        with open(WATCHLIST_PATH, "w", encoding="utf-8") as f:
            f.write(new_text)
        print("✅ Adicionados na watchlist.txt (o vigia já vai olhar eles).")
        print("   Reinicie o vigia:  sudo systemctl restart watchlist-vigia")
    else:
        print("Pra adicionar na watchlist do vigia, rode de novo com --add")
    print("=" * 60)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Top moedas em alta na Bybit (só leitura).")
    p.add_argument("-n", type=int, default=5, help="Quantas moedas (padrão 5).")
    p.add_argument("--min-vol", type=float, default=30_000_000, help="Volume 24h mínimo (USDT).")
    p.add_argument("--add", action="store_true", help="Adiciona os top-N na watchlist.txt.")
    args = p.parse_args()
    return run(args.n, args.min_vol, args.add)


if __name__ == "__main__":
    import sys
    sys.exit(main())
