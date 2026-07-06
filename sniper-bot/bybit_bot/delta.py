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
        "brain": os.getenv("DELTA_BRAIN", "true").strip().lower() in {"1", "true", "yes", "sim"},
        "brain_warn_dd": float(os.getenv("DELTA_BRAIN_WARN_DD", "0.05")),
        "brain_hard_dd": float(os.getenv("DELTA_BRAIN_HARD_DD", "0.12")),
        # realizador de lucro: fecha tudo e reabre quando o P&L aberto atinge o alvo
        "take_profit_usd": float(os.getenv("DELTA_TAKE_PROFIT_USD", "0")),   # 0 = desligado
        "stop_loss_usd": float(os.getenv("DELTA_STOP_LOSS_USD", "0")),       # 0 = desligado
        "check_sec": float(os.getenv("DELTA_CHECK_SEC", "300")),             # checa lucro a cada 5min
    }


PEAK_PATH = "delta_peak.txt"


def _load_peak(path: str = PEAK_PATH) -> float:
    try:
        with open(path, encoding="utf-8") as f:
            return float(f.read().strip())
    except (FileNotFoundError, ValueError):
        return 0.0


def _save_peak(value: float, path: str = PEAK_PATH) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"{value:.4f}")
    except OSError:
        pass


EQUITY_PATH = "delta_equity.csv"


def _record_equity(ex, path: str = EQUITY_PATH) -> None:
    """Anexa (timestamp, saldo) para o gráfico do painel. Best-effort."""
    import time
    try:
        from .status import fetch_balance_usdt
        total, _ = fetch_balance_usdt(ex)
        if total <= 0:
            return
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{int(time.time())},{total:.4f}\n")
    except Exception:  # noqa: BLE001
        pass


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
    from . import brain
    from .trader import close_position

    bal = ex.fetch_balance()
    equity = float((bal.get("USDT", {}) or {}).get("total") or 0)

    # cérebro: exposição pela queda do saldo (topo persistente)
    gross_mult = 1.0
    if dc.get("brain"):
        peak = max(_load_peak(), equity)
        _save_peak(peak)
        dd = (peak - equity) / peak if peak > 0 else 0.0
        dec = brain.exposure_for_drawdown(dd, dc["brain_warn_dd"], dc["brain_hard_dd"])
        gross_mult = dec["mult"]
        if dec["reason"] != "normal":
            log.warning("CÉREBRO DELTA: %s", dec["reason"])
        if dec["flatten"]:
            longs, shorts, rows = [], [], []      # disjuntor: fica em caixa
        else:
            longs, shorts, rows = build_target(ex, dc["k"], dc["min_vol"])
    else:
        longs, shorts, rows = build_target(ex, dc["k"], dc["min_vol"])

    cur = current_positions(ex)
    actions = rebalance_actions(cur, longs, shorts)
    n = len(longs) + len(shorts)
    notional = per_position_notional(equity, dc["gross"] * gross_mult, n)

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


def flatten(ex) -> int:
    """Fecha TODAS as posições do Delta (realiza o resultado). Retorna quantas fechou."""
    from .trader import close_position
    n = 0
    for sym in list(current_positions(ex)):
        try:
            close_position(ex, sym)
            n += 1
        except Exception as exc:  # noqa: BLE001
            log.error("Falha ao fechar %s: %s", sym, exc)
    return n


def open_pnl(ex) -> float:
    """Soma do P&L aberto (não realizado) de todas as posições."""
    from .status import fetch_open_positions
    return sum(p["pnl"] for p in fetch_open_positions(ex))


def _do_rebalance(ex, dc) -> None:
    try:
        r = rebalance_live(ex, dc)
        log.warning("Rebalance: equity=%.2f | %d abertas, %d fechadas | ~%.2f USDT/posição",
                    r["equity"], r["opened"], r["closed"], r["notional"])
    except Exception as exc:  # noqa: BLE001
        log.error("Erro no rebalance (segue tentando): %s", exc)


def _run_live(once: bool) -> int:
    import time
    dc = load_delta_config()
    ex = make_delta_client(dc)
    env = "TESTNET" if dc["testnet"] else "REAL (dinheiro de verdade)"
    log.warning("DELTA LIVE | %s | %d long + %d short | lev=%dx | vol>=%.0fM | rebal a cada %.0fh",
                env, dc["k"], dc["k"], dc["leverage"], dc["min_vol"] / 1e6, dc["rebalance_hours"])
    if dc.get("brain"):
        log.warning("CÉREBRO DELTA ligado: reduz exposição se saldo cair %.0f%%, fica em caixa se cair %.0f%%.",
                    dc["brain_warn_dd"] * 100, dc["brain_hard_dd"] * 100)
    tp, sl = dc.get("take_profit_usd", 0), dc.get("stop_loss_usd", 0)
    if tp > 0 or sl > 0:
        log.warning("REALIZADOR ligado: fecha tudo e reabre se lucro >= +$%.0f%s.",
                    tp, f" ou perda <= -${sl:.0f}" if sl > 0 else "")

    _do_rebalance(ex, dc)
    _record_equity(ex)
    if once:
        return 0
    last_rebal = time.time()
    while True:
        time.sleep(dc["check_sec"])
        _record_equity(ex)
        try:
            # realizador de lucro/perda: checa o P&L aberto a cada ciclo
            if tp > 0 or sl > 0:
                pnl = open_pnl(ex)
                if (tp > 0 and pnl >= tp) or (sl > 0 and pnl <= -sl):
                    motivo = "LUCRO" if pnl > 0 else "PERDA"
                    log.warning("REALIZADOR: %s de %+.2f USDT atingido — fecho tudo e reabro.",
                                motivo, pnl)
                    fechadas = flatten(ex)
                    log.warning("Realizei %+.2f USDT (%d posições). Nova análise...", pnl, fechadas)
                    _do_rebalance(ex, dc)
                    last_rebal = time.time()
                    continue
            # rebalance normal do ciclo (24h)
            if time.time() - last_rebal >= dc["rebalance_hours"] * 3600:
                _do_rebalance(ex, dc)
                last_rebal = time.time()
        except Exception as exc:  # noqa: BLE001
            log.error("Erro no loop Delta (segue): %s", exc)


def history() -> int:
    """Relatório dos trades FECHADOS do Delta (P&L realizado da subconta)."""
    from . import journal
    dc = load_delta_config()
    ex = make_delta_client(dc)
    closed = journal.fetch_closed(ex, limit=100)
    st = journal.compute_stats(closed)
    print("=" * 56)
    print("HISTÓRICO DO DELTA (posições fechadas)")
    print("=" * 56)
    if st["count"] == 0:
        print("Ainda não há posições fechadas (o 1º rebalance ainda não trocou nada).")
        return 0
    pf = "inf" if st["profit_factor"] == float("inf") else f"{st['profit_factor']:.2f}"
    print(f"Fechadas       : {st['count']}")
    print(f"Ganhos/Perdas  : {st['wins']}/{st['losses']}  ({st['win_rate'] * 100:.0f}% ganho)")
    print(f"P&L realizado  : {st['total_pnl']:+.4f} USDT")
    print(f"Média por trade: {st['expectancy']:+.4f} USDT | profit factor: {pf}")
    print("-" * 56)
    print("Últimas fechadas (mais recente primeiro):")
    for c in reversed(closed[-15:]):
        sym = (c["symbol"] or "?").replace("/USDT:USDT", "")
        print(f"  {sym:14s}  P&L {c['pnl']:+.4f} USDT")
    print("=" * 56)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Estratégia Delta (long/short neutro)")
    p.add_argument("--live", action="store_true",
                   help="Executa DE VERDADE na subconta Delta (senão, só simula).")
    p.add_argument("--once", action="store_true", help="Faz 1 rebalance e sai (com --live).")
    p.add_argument("--history", action="store_true", help="Mostra o histórico de fechados do Delta.")
    p.add_argument("--k", type=int, default=5, help="Moedas por lado (long e short).")
    p.add_argument("--min-vol", type=float, default=5_000_000, help="Volume 24h mínimo (USDT).")
    p.add_argument("--equity", type=float, default=40.0, help="Capital (só na simulação).")
    p.add_argument("--gross", type=float, default=1.0, help="Exposição bruta (1.0 = 1x).")
    args = p.parse_args()

    if args.history:
        return history()
    if args.live:
        return _run_live(args.once)
    return _preview(args.k, args.min_vol, args.equity, args.gross)


if __name__ == "__main__":
    import sys
    sys.exit(main())
