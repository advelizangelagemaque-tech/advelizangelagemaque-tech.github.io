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


# ---- configuração e execução real (subconta Delta, chaves separadas) -------

def load_delta_config() -> dict:
    """Lê .env.delta (chaves da SUBCONTA Delta, separadas do outro bot)."""
    import os
    try:
        from dotenv import load_dotenv
        if os.path.exists(".env.delta"):
            load_dotenv(".env.delta", override=True)
    except ImportError:  # pragma: no cover
        pass
    priv = os.getenv("DELTA_API_PRIVATE_KEY_PATH", "").strip()
    secret = os.getenv("DELTA_API_SECRET", "")
    if priv:
        path = os.path.expanduser(priv)
        if not os.path.exists(path):
            raise ValueError(f"DELTA_API_PRIVATE_KEY_PATH não encontrado: {path}")
        with open(path, encoding="utf-8") as f:
            secret = f.read()
    return {
        "api_key": os.getenv("DELTA_API_KEY", ""),
        "secret": secret,
        "testnet": os.getenv("DELTA_TESTNET", "false").strip().lower() in {"1", "true", "yes", "sim"},
        "k": int(os.getenv("DELTA_K", "5")),
        "min_vol": float(os.getenv("DELTA_MIN_VOL", "5000000")),
        "gross": float(os.getenv("DELTA_GROSS", "1.0")),
        "leverage": int(os.getenv("DELTA_LEVERAGE", "1")),
        "rebalance_hours": float(os.getenv("DELTA_REBALANCE_HOURS", "24")),
    }


def make_delta_client(dc: dict):
    import ccxt
    if not dc["api_key"] or not dc["secret"]:
        raise ValueError("Faltam chaves da subconta Delta. Configure DELTA_API_KEY e "
                         "DELTA_API_PRIVATE_KEY_PATH em .env.delta.")
    ex = ccxt.bybit({"apiKey": dc["api_key"], "secret": dc["secret"],
                     "enableRateLimit": True, "options": {"defaultType": "swap"}})
    if dc["testnet"]:
        ex.set_sandbox_mode(True)
    return ex


def current_positions(ex) -> dict:
    """{symbol: 'long'|'short'} das posições abertas."""
    out = {}
    try:
        for p in ex.fetch_positions():
            c = float(p.get("contracts") or 0)
            if c != 0:
                out[p.get("symbol")] = (p.get("side") or "").lower()
    except Exception as exc:  # noqa: BLE001
        log.warning("Não consegui listar posições: %s", exc)
    return out


def _open(ex, symbol: str, side: str, notional: float, leverage: int) -> None:
    from .trader import set_leverage_safe
    set_leverage_safe(ex, leverage, symbol)
    price = float(ex.fetch_ticker(symbol)["last"])
    if price <= 0 or notional <= 0:
        raise ValueError("preço/notional inválido")
    qty = float(ex.amount_to_precision(symbol, notional / price))
    order_side = "buy" if side == "long" else "sell"
    ex.create_order(symbol, "market", order_side, qty)


def rebalance_live(ex, dc: dict) -> dict:
    """Executa o rebalanceamento na subconta Delta. Retorna um resumo."""
    from .trader import close_position
    longs, shorts, rows = build_target(ex, dc["k"], dc["min_vol"])
    cur = current_positions(ex)
    actions = rebalance_actions(cur, longs, shorts)

    bal = ex.fetch_balance()
    equity = float((bal.get("USDT", {}) or {}).get("total") or 0)
    n = len(longs) + len(shorts)
    notional = per_position_notional(equity, dc["gross"], n)

    closed = opened = 0
    for kind, sym, side in actions:      # fecha primeiro (libera margem)
        if kind == "close":
            try:
                close_position(ex, sym)
                closed += 1
                log.warning("FECHOU %s (%s)", sym, side)
            except Exception as exc:  # noqa: BLE001
                log.error("Falha ao fechar %s: %s", sym, exc)
    for kind, sym, side in actions:
        if kind == "open":
            try:
                _open(ex, sym, side, notional, dc["leverage"])
                opened += 1
                log.warning("ABRIU %s %s | ~%.2f USDT (1x)", side.upper(), sym, notional)
            except Exception as exc:  # noqa: BLE001
                log.error("Falha ao abrir %s %s: %s", side, sym, exc)
    return {"equity": equity, "longs": longs, "shorts": shorts,
            "closed": closed, "opened": opened, "notional": notional}


def _preview(k: int, min_vol: float, equity: float, gross: float) -> int:
    ex = _public_client()
    log.warning("Montando cesta Delta: %d long + %d short | vol24h >= %.0fM USDT ...",
                k, k, min_vol / 1e6)
    longs, shorts, rows = build_target(ex, k, min_vol)
    if not longs and not shorts:
        log.warning("Sem ativos suficientes com esse filtro de volume.")
        return 0
    n = len(longs) + len(shorts)
    size = per_position_notional(equity, gross, n)
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


def _run_live(once: bool) -> int:
    import time
    dc = load_delta_config()
    ex = make_delta_client(dc)
    env = "TESTNET" if dc["testnet"] else "REAL (dinheiro de verdade)"
    log.warning("DELTA LIVE | %s | %d long + %d short | lev=%dx | vol>=%.0fM | rebal a cada %.0fh",
                env, dc["k"], dc["k"], dc["leverage"], dc["min_vol"] / 1e6, dc["rebalance_hours"])
    while True:
        try:
            r = rebalance_live(ex, dc)
            log.warning("Rebalance: equity=%.2f | %d abertas, %d fechadas | ~%.2f USDT/posição",
                        r["equity"], r["opened"], r["closed"], r["notional"])
        except Exception as exc:  # noqa: BLE001
            log.error("Erro no rebalance (segue tentando): %s", exc)
        if once:
            return 0
        time.sleep(dc["rebalance_hours"] * 3600)


def main() -> int:
    p = argparse.ArgumentParser(description="Estratégia Delta (long/short neutro)")
    p.add_argument("--live", action="store_true",
                   help="Executa DE VERDADE na subconta Delta (senão, só simula).")
    p.add_argument("--once", action="store_true", help="Faz 1 rebalance e sai (com --live).")
    p.add_argument("--k", type=int, default=5, help="Moedas por lado (long e short).")
    p.add_argument("--min-vol", type=float, default=5_000_000, help="Volume 24h mínimo (USDT).")
    p.add_argument("--equity", type=float, default=40.0, help="Capital (só na simulação).")
    p.add_argument("--gross", type=float, default=1.0, help="Exposição bruta (1.0 = 1x).")
    args = p.parse_args()

    if args.live:
        return _run_live(args.once)
    return _preview(args.k, args.min_vol, args.equity, args.gross)


if __name__ == "__main__":
    import sys
    sys.exit(main())
