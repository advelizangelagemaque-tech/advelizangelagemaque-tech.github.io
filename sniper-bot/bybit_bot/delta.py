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

def eligible_rows(tickers: dict, min_vol_usdt: float, by_funding: bool = False) -> list[dict]:
    """Perps USDT líquidos: [{symbol, score, vol, funding}].

    by_funding=False: score = alta 24h (momentum).
    by_funding=True : score = -funding. Assim, no rank_basket, o TOP-k (score alto =
    funding mais NEGATIVO) vira LONG — que RECEBE quando o funding é negativo — e o
    BOTTOM-k (funding mais POSITIVO) vira SHORT — que RECEBE quando é positivo.
    Resultado: cesta neutra que COLHE funding dos dois lados.
    """
    rows = []
    for sym, t in tickers.items():
        if not sym.endswith(":USDT"):
            continue
        vol = t.get("quoteVolume") or t.get("baseVolume")
        if vol is None or float(vol) < min_vol_usdt:
            continue
        if by_funding:
            fr = (t.get("info") or {}).get("fundingRate")
            if fr in (None, ""):
                continue
            fr = float(fr)
            rows.append({"symbol": sym, "score": -fr, "vol": float(vol), "funding": fr})
        else:
            pct = t.get("percentage")
            if pct is None:
                continue
            rows.append({"symbol": sym, "score": pct / 100.0, "vol": float(vol), "funding": None})
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

SKIP_PATH = "delta_skip.txt"


def _load_skip(path: str = SKIP_PATH) -> set[str]:
    """Tokens permanentemente fora da cesta (ex: exigem acordo manual na Bybit)."""
    try:
        with open(path, encoding="utf-8") as f:
            return {ln.strip() for ln in f if ln.strip()}
    except FileNotFoundError:
        return set()


def _add_skip(sym: str, path: str = SKIP_PATH) -> None:
    if sym not in _load_skip(path):
        with open(path, "a", encoding="utf-8") as f:
            f.write(sym + "\n")


def build_target(ex, k: int, min_vol_usdt: float,
                 by_funding: bool = False) -> tuple[list[str], list[str], list[dict]]:
    tickers = ex.fetch_tickers()
    rows = eligible_rows(tickers, min_vol_usdt, by_funding=by_funding)
    skip = _load_skip()                                  # fora os que exigem acordo etc.
    rows = [r for r in rows if r["symbol"] not in skip]
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
        # colheita de funding: escolhe os lados para RECEBER o pagamento de funding
        "funding_mode": os.getenv("DELTA_FUNDING", "false").strip().lower() in {"1", "true", "yes", "sim"},
        # stop por posição: fecha UMA perna que cair mais que isso (0.25 = -25%). Protege
        # contra uma única moeda explodir (a lição da TAC). 0 = desligado.
        "pos_stop": float(os.getenv("DELTA_POS_STOP", "0.25")),
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


# ---- contabilidade real: aportes/retiradas (livro-caixa) -------------------
# O gráfico de saldo sozinho ENGANA: quando você deposita, o saldo pula e parece
# lucro — mas é dinheiro seu que entrou. Aqui guardamos os aportes para calcular
# o lucro REAL = valor atual - total depositado.

DEPOSITS_PATH = "delta_deposits.csv"


def record_deposit(amount: float, at_start: bool = False, ts: int | None = None,
                   path: str = DEPOSITS_PATH) -> None:
    """Registra um aporte (+) ou retirada (-). at_start=True marca com timestamp 0
    (dinheiro que já estava na conta antes de começarmos a medir no tempo).
    ts explícito vence (usado para 'encaixar' o registro no pulo real do saldo)."""
    import time
    if ts is None:
        ts = 0 if at_start else int(time.time())
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{ts},{amount:.4f}\n")


def aligned_deposit_ts(amount: float, equity_path: str = EQUITY_PATH) -> int:
    """Acha na série de saldo o instante em que o saldo pulou/caiu ~amount (o
    depósito ou saque de verdade) e devolve ESSE timestamp. Assim o gráfico não
    confunde o aporte com lucro. Se não achar um pulo parecido, usa agora."""
    import time
    now = int(time.time())
    try:
        pts: list[tuple[int, float]] = []
        with open(equity_path, encoding="utf-8") as f:
            for line in f:
                a = line.strip().split(",")
                if len(a) == 2:
                    pts.append((int(a[0]), float(a[1])))
    except (FileNotFoundError, ValueError):
        return now
    tol = max(2.0, abs(amount) * 0.2)      # tolerância: 20% do valor (ou 2 USDT)
    best_ts, best_diff = now, tol
    for (_, v0), (t1, v1) in zip(pts, pts[1:]):
        jump = v1 - v0
        if (amount > 0 and jump > 0) or (amount < 0 and jump < 0):
            d = abs(jump - amount)
            if d < best_diff:
                best_diff, best_ts = d, t1
    return best_ts


def deposits_timeline(path: str = DEPOSITS_PATH) -> list[tuple[int, float]]:
    """Lista ordenada de (timestamp, valor) dos aportes/retiradas."""
    out: list[tuple[int, float]] = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split(",")
                if len(parts) == 2:
                    out.append((int(float(parts[0])), float(parts[1])))
    except (FileNotFoundError, ValueError):
        return []
    out.sort(key=lambda x: x[0])
    return out


def net_deposits(path: str = DEPOSITS_PATH) -> float:
    """Total líquido colocado por você (aportes menos retiradas)."""
    return sum(a for _, a in deposits_timeline(path))


def gross_deposits(path: str = DEPOSITS_PATH) -> float:
    """Só o que você COLOCOU (soma dos aportes, ignorando saques)."""
    return sum(a for _, a in deposits_timeline(path) if a > 0)


def total_withdrawn(path: str = DEPOSITS_PATH) -> float:
    """Só o que você TIROU (soma dos saques, em positivo) — seu lucro no bolso."""
    return sum(-a for _, a in deposits_timeline(path) if a < 0)


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


def excess_to_close(positions: list[dict]) -> list[str]:
    """Mantém a neutralidade: se um lado tem mais posições que o outro, devolve os
    símbolos do lado MAIS PESADO a fechar (os piores em P&L primeiro). Puro/testável."""
    longs = [p for p in positions if (p.get("side") or "").lower() == "long"]
    shorts = [p for p in positions if (p.get("side") or "").lower() == "short"]
    diff = len(longs) - len(shorts)
    if diff == 0:
        return []
    heavier = longs if diff > 0 else shorts
    heavier = sorted(heavier, key=lambda p: p.get("pnl", 0.0))   # pior P&L primeiro
    return [p["symbol"] for p in heavier[:abs(diff)]]


def _enforce_neutral(ex) -> int:
    """Fecha o excesso do lado mais pesado para o livro voltar a ser neutro."""
    from .status import fetch_open_positions
    from .trader import close_position
    try:
        positions = fetch_open_positions(ex)
    except Exception as exc:  # noqa: BLE001
        log.warning("Não consegui checar o equilíbrio: %s", exc)
        return 0
    alvo = excess_to_close(positions)
    fechadas = 0
    for sym in alvo:
        try:
            close_position(ex, sym)
            fechadas += 1
            log.warning("NEUTRALIZA: fechei %s para reequilibrar long/short.", sym)
        except Exception as exc:  # noqa: BLE001
            log.error("Falha ao neutralizar %s: %s", sym, exc)
    return fechadas


def leg_stop_hit(entry: float, mark: float, side: str, leverage: int, stop: float) -> bool:
    """True se ESTA perna caiu mais que `stop` (ex: 0.25 = -25% de ROI). Pura/testável.
    ROI = variação de preço × alavancagem (short lucra quando o preço CAI)."""
    if entry <= 0 or stop <= 0:
        return False
    change = (mark - entry) / entry
    roi = change * leverage if side == "long" else -change * leverage
    return roi <= -stop


def _stop_bad_legs(ex, dc: dict) -> int:
    """Fecha qualquer perna que estourou o stop por posição e reequilibra a cesta.
    Impede que uma única moeda (tipo a TAC) abra um buraco grande sozinha."""
    stop = dc.get("pos_stop", 0.0)
    if stop <= 0:
        return 0
    from .status import fetch_open_positions
    from .trader import close_position
    try:
        positions = fetch_open_positions(ex)
    except Exception:  # noqa: BLE001
        return 0
    fechadas = 0
    for p in positions:
        if leg_stop_hit(p.get("entry", 0.0), p.get("mark", 0.0),
                        (p.get("side") or "").lower(), dc["leverage"], stop):
            try:
                close_position(ex, p["symbol"])
                fechadas += 1
                log.warning("STOP POSIÇÃO: %s (%s) estourou o stop de -%.0f%% — fecho só ela.",
                            p["symbol"], p.get("side"), stop * 100)
            except Exception as exc:  # noqa: BLE001
                log.error("Falha no stop de %s: %s", p["symbol"], exc)
    if fechadas:
        _enforce_neutral(ex)          # reequilibra o que sobrou (mantém neutro)
    return fechadas


def _open_side_to_k(ex, dc: dict, rows: list[dict], side: str, k: int,
                    notional: float, skip: set) -> int:
    """Abre posições do lado `side` até conseguir k VÁLIDAS, descendo a lista de
    força (LONG começa nas mais fortes; SHORT nas mais fracas) e pulando as que
    exigem acordo (que ficam na skip-list). Devolve quantas abriu."""
    if k <= 0 or not rows:
        return 0
    ranked = sorted(rows, key=lambda r: -r["score"])
    if side == "short":
        ranked = list(reversed(ranked))
    cur = current_positions(ex)
    have = sum(1 for sd in cur.values() if sd == side)
    abertas = 0
    for r in ranked:
        if have >= k:
            break
        sym = r["symbol"]
        if sym in skip or sym in cur:                # já pulado ou já aberto
            continue
        try:
            _open(ex, sym, side, notional, dc["leverage"])
            have += 1
            abertas += 1
            cur[sym] = side
            log.warning("ABRIU %s %s | ~%.2f USDT (1x)", side.upper(), sym, notional)
        except Exception as exc:  # noqa: BLE001
            log.error("Falha ao abrir %s %s: %s", side, sym, exc)
            if "110126" in str(exc) or "sign the required agreement" in str(exc):
                _add_skip(sym)
                skip.add(sym)
                log.warning("PULO PERMANENTE: %s exige acordo manual na Bybit — "
                            "fora da cesta a partir de agora.", sym)
    return abertas


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
            longs, shorts, rows = build_target(ex, dc["k"], dc["min_vol"],
                                               by_funding=dc.get("funding_mode", False))
    else:
        longs, shorts, rows = build_target(ex, dc["k"], dc["min_vol"])

    cur = current_positions(ex)
    actions = rebalance_actions(cur, longs, shorts)
    n = len(longs) + len(shorts)
    notional = per_position_notional(equity, dc["gross"] * gross_mult, n)

    closed = 0
    for kind, sym, side in actions:      # fecha primeiro (libera margem)
        if kind == "close":
            try:
                close_position(ex, sym)
                closed += 1
                log.warning("FECHOU %s (%s)", sym, side)
            except Exception as exc:  # noqa: BLE001
                log.error("Falha ao fechar %s: %s", sym, exc)
    # abre preenchendo cada lado até k VÁLIDAS (desce a lista e pula as que exigem
    # acordo) — assim a cesta fica CHEIA mesmo com tokens problemáticos.
    skip = _load_skip()
    opened = (_open_side_to_k(ex, dc, rows, "long", dc["k"], notional, skip)
              + _open_side_to_k(ex, dc, rows, "short", dc["k"], notional, skip))
    # trava final de neutralidade: se um lado não alcançar k, equilibra o outro.
    neutralized = _enforce_neutral(ex)
    return {"equity": equity, "longs": longs, "shorts": shorts, "closed": closed,
            "opened": opened, "notional": notional, "neutralized": neutralized}


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
    if dc.get("funding_mode"):
        log.warning("COLHEITA DE FUNDING ligada: shorta os perps de funding mais ALTO e "
                    "longa os de funding mais BAIXO/negativo — recebe o funding dos dois lados.")
    if dc.get("brain"):
        log.warning("CÉREBRO DELTA ligado: reduz exposição se saldo cair %.0f%%, fica em caixa se cair %.0f%%.",
                    dc["brain_warn_dd"] * 100, dc["brain_hard_dd"] * 100)
    tp, sl = dc.get("take_profit_usd", 0), dc.get("stop_loss_usd", 0)
    if tp > 0 or sl > 0:
        log.warning("REALIZADOR ligado: fecha tudo e reabre se lucro >= +$%.0f%s.",
                    tp, f" ou perda <= -${sl:.0f}" if sl > 0 else "")
    if dc.get("pos_stop", 0) > 0:
        log.warning("STOP POR POSIÇÃO ligado: fecha qualquer perna que cair mais de -%.0f%% "
                    "(protege contra uma moeda explodir sozinha).", dc["pos_stop"] * 100)

    _do_rebalance(ex, dc)
    _record_equity(ex)
    if once:
        return 0
    last_rebal = time.time()
    while True:
        time.sleep(dc["check_sec"])
        _record_equity(ex)
        try:
            # stop por posição: corta qualquer perna que explodiu (antes de tudo)
            if _stop_bad_legs(ex, dc):
                continue
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


def _delta_value() -> tuple[float, float, float]:
    """(valor_atual, saldo, pnl_aberto) — valor = o que você teria fechando tudo."""
    dc = load_delta_config()
    ex = make_delta_client(dc)
    from .status import fetch_balance_usdt, fetch_open_positions
    total, _ = fetch_balance_usdt(ex)
    open_p = sum(p["pnl"] for p in fetch_open_positions(ex))
    return total + open_p, total, open_p


def ledger_report() -> int:
    """Contabilidade real: depositado, sacado (no bolso) e lucro total."""
    value, total, open_p = _delta_value()
    aportes = gross_deposits()
    sacado = total_withdrawn()
    print("=" * 56)
    print("CONTABILIDADE DO DELTA (desde o 1º depósito)")
    print("=" * 56)
    if aportes <= 0:
        print("Ainda não há aportes registrados.")
        print("Registre o que você já depositou com:")
        print("  python -m bybit_bot.delta --deposit VALOR --at-start")
        print("=" * 56)
        return 0
    # lucro total = tudo que você tem hoje + o que já sacou - tudo que colocou
    lucro = value + sacado - aportes
    base = aportes - sacado                      # principal ainda trabalhando
    pct = lucro / aportes * 100 if aportes > 0 else 0.0
    disp = max(0.0, value - base)                # lucro disponível p/ sacar hoje
    rotulo = "LUCRO TOTAL" if lucro >= 0 else "PREJUÍZO TOTAL"
    print(f"Você depositou   : {aportes:.2f} USDT")
    print(f"Já sacou (bolso) : {sacado:.2f} USDT")
    print(f"Vale hoje        : {value:.2f} USDT   (saldo {total:.2f} + aberto {open_p:+.2f})")
    print(f"{rotulo:16s} : {lucro:+.2f} USDT   ({pct:+.1f}%)")
    print("-" * 56)
    print(f"Disponível p/ sacar agora (mantendo o principal): {disp:.2f} USDT")
    print("=" * 56)
    return 0


def saque_report(fracao: float) -> int:
    """Sugere quanto sacar hoje: uma fração do lucro que está na conta.
    O resto continua investido (reinveste/compõe sozinho no próximo rebalance)."""
    value, _, _ = _delta_value()
    aportes = gross_deposits()
    sacado = total_withdrawn()
    base = aportes - sacado
    lucro_na_conta = value - base
    print("=" * 56)
    print("SAQUE SEMANAL DO DELTA")
    print("=" * 56)
    if aportes <= 0:
        print("Registre primeiro seus aportes: --deposit VALOR --at-start")
        print("=" * 56)
        return 0
    if lucro_na_conta <= 0:
        print(f"Sem lucro para sacar agora (lucro na conta: {lucro_na_conta:+.2f} USDT).")
        print("Espera acumular. Nada a fazer neste sábado. 🙂")
        print("=" * 56)
        return 0
    sugestao = lucro_na_conta * fracao
    print(f"Lucro na conta agora : {lucro_na_conta:.2f} USDT")
    print(f"Regra                : sacar {fracao * 100:.0f}% do lucro, reinvestir o resto")
    print(f"👉 Saque sugerido    : {sugestao:.2f} USDT")
    print(f"   (fica investido)  : {lucro_na_conta - sugestao:.2f} USDT de lucro + {base:.2f} principal")
    print("-" * 56)
    print("Passo a passo:")
    print(f"  1) Na Bybit: transfira {sugestao:.2f} USDT da subconta Delta p/ sua conta principal")
    print(f"  2) Aqui, registre o saque:  python -m bybit_bot.delta --withdraw {sugestao:.2f}")
    print("=" * 56)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Estratégia Delta (long/short neutro)")
    p.add_argument("--live", action="store_true",
                   help="Executa DE VERDADE na subconta Delta (senão, só simula).")
    p.add_argument("--once", action="store_true", help="Faz 1 rebalance e sai (com --live).")
    p.add_argument("--history", action="store_true", help="Mostra o histórico de fechados do Delta.")
    p.add_argument("--flatten", action="store_true",
                   help="Fecha TODAS as posições do Delta agora (para pausar limpo).")
    p.add_argument("--ledger", action="store_true",
                   help="Contabilidade real: depositado, sacado e lucro total.")
    p.add_argument("--saque", nargs="?", type=float, const=1.0, default=None, metavar="FRACAO",
                   help="Sugere o saque semanal (fração do lucro; padrão 1.0 = todo o lucro).")
    p.add_argument("--deposit", type=float, default=None, metavar="USDT",
                   help="Registra um APORTE (dinheiro que você colocou).")
    p.add_argument("--withdraw", type=float, default=None, metavar="USDT",
                   help="Registra uma RETIRADA/saque (dinheiro que você tirou).")
    p.add_argument("--at-start", action="store_true",
                   help="Marca o aporte como saldo que JÁ existia antes de medir.")
    p.add_argument("--k", type=int, default=5, help="Moedas por lado (long e short).")
    p.add_argument("--min-vol", type=float, default=5_000_000, help="Volume 24h mínimo (USDT).")
    p.add_argument("--equity", type=float, default=40.0, help="Capital (só na simulação).")
    p.add_argument("--gross", type=float, default=1.0, help="Exposição bruta (1.0 = 1x).")
    args = p.parse_args()

    if args.deposit is not None:
        ts = None if args.at_start else aligned_deposit_ts(args.deposit)
        record_deposit(args.deposit, at_start=args.at_start, ts=ts)
        extra = " (saldo inicial)" if args.at_start else ""
        print(f"✅ Aporte registrado: +{args.deposit:.2f} USDT{extra}. "
              f"Total depositado: {gross_deposits():.2f} USDT.")
        return 0
    if args.withdraw is not None:
        ts = aligned_deposit_ts(-args.withdraw)
        record_deposit(-args.withdraw, ts=ts)
        print(f"✅ Saque registrado: -{args.withdraw:.2f} USDT. "
              f"Total já sacado (no bolso): {total_withdrawn():.2f} USDT.")
        return 0
    if args.ledger:
        return ledger_report()
    if args.saque is not None:
        return saque_report(args.saque)
    if args.history:
        return history()
    if args.flatten:
        dc = load_delta_config()
        ex = make_delta_client(dc)
        n = flatten(ex)
        print(f"✅ Fechei {n} posição(ões) do Delta. Livro zerado — pode pausar em paz.")
        return 0
    if args.live:
        return _run_live(args.once)
    return _preview(args.k, args.min_vol, args.equity, args.gross)


if __name__ == "__main__":
    import sys
    sys.exit(main())
