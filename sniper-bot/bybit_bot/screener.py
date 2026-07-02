"""Rastreador (screener) da estratégia 'comprar o dip em tendência de alta'.

Usa APENAS dados públicos da Bybit (via ccxt) — sem chave e sem enviar ordens.
Serve para você VER quais tokens a estratégia escolheria agora, sem risco.

Regra:
  1. perp USDT com variação 24h entre MIN e MAX (tendência de alta forte);
  2. que esteja num pullback: o preço recuou >= DIP_MIN a partir da máxima recente.
"""

from __future__ import annotations

import argparse
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("bybit_bot.screener")


def make_public_client():
    import ccxt
    return ccxt.bybit({"options": {"defaultType": "swap"}, "enableRateLimit": True})


# ---- lógica pura (testável) ------------------------------------------------

def passes_trend(pct_24h: float, min_pct: float, max_pct: float) -> bool:
    """True se a alta de 24h está na faixa desejada (frações: 0.20 = 20%)."""
    return min_pct <= pct_24h <= max_pct


def compute_dip(highs: list[float], last: float) -> float:
    """Quanto o preço recuou (fração) a partir da máxima recente."""
    hi = max(highs) if highs else last
    return (hi - last) / hi if hi > 0 else 0.0


def is_entry(pct_24h: float, dip: float, cfg) -> bool:
    dip_max = getattr(cfg, "dip_max", 1.0)
    return (passes_trend(pct_24h, cfg.min_24h, cfg.max_24h)
            and cfg.dip_min <= dip <= dip_max)


# ---- coleta (rede pública) -------------------------------------------------

def find_candidates(ex, cfg, timeframe: str = "5m", lookback: int = 12) -> list[dict]:
    """Retorna os tokens que passam na estratégia agora (ordenados por alta 24h)."""
    tickers = ex.fetch_tickers()
    out: list[dict] = []
    for sym, t in tickers.items():
        if not sym.endswith(":USDT"):          # só perps lineares USDT
            continue
        pct = t.get("percentage")
        if pct is None:
            continue
        pct = pct / 100.0                       # ccxt dá em % (ex.: 23.5)
        if not passes_trend(pct, cfg.min_24h, cfg.max_24h):
            continue
        try:
            ohlcv = ex.fetch_ohlcv(sym, timeframe, limit=lookback)
        except Exception:  # noqa: BLE001
            continue
        if not ohlcv:
            continue
        highs = [c[2] for c in ohlcv]
        last = ohlcv[-1][4]
        dip = compute_dip(highs, last)
        dip_max = getattr(cfg, "dip_max", 1.0)
        if cfg.dip_min <= dip <= dip_max:
            out.append({"symbol": sym, "pct_24h": pct, "dip": dip, "last": last})
    return sorted(out, key=lambda x: -x["pct_24h"])


def _default_cfg(args):
    from types import SimpleNamespace
    return SimpleNamespace(min_24h=args.min_24h, max_24h=args.max_24h, dip_min=args.dip_min)


def main() -> int:
    p = argparse.ArgumentParser(description="Rastreador Bybit (dip em alta) — dados públicos")
    p.add_argument("--min-24h", type=float, default=0.20, help="Alta mínima 24h (0.20 = 20%%).")
    p.add_argument("--max-24h", type=float, default=0.50, help="Alta máxima 24h (0.50 = 50%%).")
    p.add_argument("--dip-min", type=float, default=0.03, help="Recuo mínimo do topo (0.03 = 3%%).")
    args = p.parse_args()
    cfg = _default_cfg(args)

    ex = make_public_client()
    log.warning("Rastreando perps USDT com alta 24h %.0f%%-%.0f%% e dip >= %.0f%% ...",
                cfg.min_24h * 100, cfg.max_24h * 100, cfg.dip_min * 100)
    cands = find_candidates(ex, cfg)
    if not cands:
        log.warning("Nenhum candidato agora (mercado sem tokens nessa faixa/dip).")
        return 0
    log.warning("Candidatos (a estratégia COMPRARIA estes agora):")
    for c in cands:
        log.warning("  %-22s | 24h +%.0f%% | dip -%.1f%% | preço %s",
                    c["symbol"], c["pct_24h"] * 100, c["dip"] * 100, c["last"])
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
