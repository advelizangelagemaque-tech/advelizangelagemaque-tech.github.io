"""Estratégia estilo 'Delta': portfólio LONG/SHORT neutro, rebalanceado, 1x.

Inspirada no Delta IA (Empiricus): em vez de apostar na direção do mercado,
monta uma cesta com as N moedas mais FORTES (compra/long) e as N mais FRACAS
(venda/short). Com long e short equilibrados, fica ~neutro de mercado: se tudo
cai, os shorts lucram e compensam; se sobe, os longs lucram. 1x = sem
liquidação.

Este módulo tem a lógica PURA (rankear, montar cesta, calcular rebalance) e um
modo SIMULAÇÃO (--dry-run) que só MOSTRA a cesta — não envia ordens.
"""

from __future__ import annotations

import argparse
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("bybit_bot.delta")


# ---- lógica pura (testável) ------------------------------------------------

def eligible_rows(tickers: dict, min_vol_usdt: float) -> list[dict]:
    """Perps USDT líquidos: [{symbol, score(=alta 24h fração), vol}]."""
    rows = []
    for sym, t in tickers.items():
        if not sym.endswith(":USDT"):
            continue
        pct = t.get("percentage")
        if pct is None:
            continue
        vol = t.get("quoteVolume")
        if vol is None:
            vol = t.get("baseVolume")
        if vol is None or float(vol) < min_vol_usdt:
            continue
        rows.append({"symbol": sym, "score": pct / 100.0, "vol": float(vol)})
    return rows


def rank_basket(rows: list[dict], k: int) -> tuple[list[str], list[str]]:
    """Top-k por força = LONG; bottom-k = SHORT. Sem sobreposição."""
    s = sorted(rows, key=lambda r: -r["score"])
    if len(s) < 2 * k:                      # poucos ativos: encolhe a cesta
        k = len(s) // 2
    if k <= 0:
        return [], []
    longs = [r["symbol"] for r in s[:k]]
    shorts = [r["symbol"] for r in s[-k:]]
    longset = set(longs)
    shorts = [x for x in shorts if x not in longset]
    return longs, shorts


def per_position_notional(equity: float, gross_exposure: float, n_positions: int) -> float:
    """Tamanho (USDT) de cada posição, dividindo a exposição igualmente."""
    if n_positions <= 0:
        return 0.0
    return equity * gross_exposure / n_positions


def rebalance_actions(current: dict, target_longs: list[str],
                      target_shorts: list[str]) -> list[tuple]:
    """Ações para sair da carteira atual e chegar na alvo.

    current: {symbol: 'long'|'short'}. Retorna [('close', sym, side), ('open', sym, side)].
    Fecha o que não pertence mais (ou está no lado errado) e abre o que falta.
    """
    tl, ts = set(target_longs), set(target_shorts)
    actions = []
    for sym, side in current.items():
        want = "long" if sym in tl else ("short" if sym in ts else None)
        if want != side:
            actions.append(("close", sym, side))
    for sym in target_longs:
        if current.get(sym) != "long":
            actions.append(("open", sym, "long"))
    for sym in target_shorts:
        if current.get(sym) != "short":
            actions.append(("open", sym, "short"))
    return actions


# ---- simulação (dry-run) ---------------------------------------------------

def build_target(ex, k: int, min_vol_usdt: float) -> tuple[list[str], list[str], list[dict]]:
    tickers = ex.fetch_tickers()
    rows = eligible_rows(tickers, min_vol_usdt)
    longs, shorts = rank_basket(rows, k)
    return longs, shorts, rows


def _public_client():
    import ccxt
    return ccxt.bybit({"options": {"defaultType": "swap"}, "enableRateLimit": True})


def main() -> int:
    p = argparse.ArgumentParser(description="Estratégia Delta (long/short neutro) — simulação")
    p.add_argument("--dry-run", action="store_true", default=True,
                   help="Só mostra a cesta; NÃO envia ordens (padrão).")
    p.add_argument("--k", type=int, default=5, help="Quantas moedas por lado (long e short).")
    p.add_argument("--min-vol", type=float, default=5_000_000,
                   help="Volume 24h mínimo em USDT (liquidez).")
    p.add_argument("--equity", type=float, default=120.0,
                   help="Capital para dimensionar as posições (só exibição).")
    p.add_argument("--gross", type=float, default=1.0, help="Exposição bruta total (1.0 = 1x).")
    args = p.parse_args()

    ex = _public_client()
    log.warning("Montando cesta Delta: %d long + %d short | vol24h >= %.0fM USDT ...",
                args.k, args.k, args.min_vol / 1e6)
    longs, shorts, rows = build_target(ex, args.k, args.min_vol)
    if not longs and not shorts:
        log.warning("Sem ativos suficientes com esse filtro de volume.")
        return 0
    n = len(longs) + len(shorts)
    size = per_position_notional(args.equity, args.gross, n)
    by = {r["symbol"]: r for r in rows}

    log.warning("Universo elegível: %d perps | cesta: %d posições | ~%.2f USDT cada",
                len(rows), n, size)
    log.warning("--- LONG (mais fortes) ---")
    for s in longs:
        log.warning("  compra %-22s | 24h %+.1f%%", s, by[s]["score"] * 100)
    log.warning("--- SHORT (mais fracos) ---")
    for s in shorts:
        log.warning("  vende  %-22s | 24h %+.1f%%", s, by[s]["score"] * 100)
    log.warning("Exposição líquida ~0 (neutro de mercado). 1x = sem liquidação.")
    log.warning("[SIMULAÇÃO] Nenhuma ordem enviada.")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
