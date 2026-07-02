"""Diário de operações do agente Bybit + estatísticas (o 'aprendizado').

Duas fontes:
  1. Registramos cada ABERTURA num CSV local (bybit_opens.csv), guardando as
     condições de mercado no momento (alta 24h e tamanho do dip).
  2. O RESULTADO (lucro/prejuízo realizado) vem da própria Bybit
     (fetch_positions_history / closed-pnl), que é a fonte da verdade.

Cruzando os dois, dá pra ver QUAIS condições deram mais lucro — e é isso que o
ajuste automático usa (quando houver amostra suficiente).
"""

from __future__ import annotations

import csv
import logging
import os

log = logging.getLogger("bybit_bot.journal")

OPENS_CSV = "bybit_opens.csv"
_FIELDS = ["ts", "symbol", "entry", "tp", "sl", "pct_24h", "dip", "qty"]


# ---- registro de aberturas -------------------------------------------------

def record_open(row: dict, path: str = OPENS_CSV) -> None:
    """Acrescenta uma abertura ao CSV (cria o cabeçalho se for a 1ª vez)."""
    novo = not os.path.exists(path)
    try:
        with open(path, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=_FIELDS)
            if novo:
                w.writeheader()
            w.writerow({k: row.get(k, "") for k in _FIELDS})
    except Exception as exc:  # noqa: BLE001
        log.warning("Não consegui gravar o diário: %s", exc)


def load_opens(path: str = OPENS_CSV) -> list[dict]:
    try:
        with open(path, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except FileNotFoundError:
        return []


# ---- resultados realizados (da Bybit) --------------------------------------

def fetch_closed(ex, limit: int = 100) -> list[dict]:
    """Trades fechados com P&L realizado, normalizados e ordenados por tempo."""
    try:
        raw = ex.fetch_positions_history(limit=limit)
    except Exception as exc:  # noqa: BLE001
        log.warning("Não consegui ler o histórico de posições: %s", exc)
        return []
    out = []
    for p in raw:
        info = p.get("info", {}) or {}
        try:
            pnl = float(p.get("realizedPnl") if p.get("realizedPnl") is not None
                        else info.get("closedPnl", 0))
        except (TypeError, ValueError):
            pnl = 0.0
        out.append({
            "symbol": p.get("symbol") or info.get("symbol"),
            "pnl": pnl,
            "entry": float(info.get("avgEntryPrice") or 0),
            "exit": float(info.get("avgExitPrice") or 0),
            "qty": float(info.get("qty") or 0),
            "ts": int(info.get("createdTime") or p.get("timestamp") or 0),
        })
    return sorted(out, key=lambda x: x["ts"])


# ---- estatísticas (puras) --------------------------------------------------

def compute_stats(closed: list[dict]) -> dict:
    """Métricas de desempenho a partir dos trades fechados."""
    n = len(closed)
    if n == 0:
        return {"count": 0, "wins": 0, "losses": 0, "win_rate": 0.0, "total_pnl": 0.0,
                "avg_win": 0.0, "avg_loss": 0.0, "expectancy": 0.0, "profit_factor": 0.0}
    wins = [c["pnl"] for c in closed if c["pnl"] > 0]
    losses = [c["pnl"] for c in closed if c["pnl"] < 0]
    total = sum(c["pnl"] for c in closed)
    gross_win = sum(wins)
    gross_loss = -sum(losses)
    return {
        "count": n,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / n,
        "total_pnl": total,
        "avg_win": (gross_win / len(wins)) if wins else 0.0,
        "avg_loss": (-gross_loss / len(losses)) if losses else 0.0,
        "expectancy": total / n,
        "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else float("inf"),
    }


def _match_open(sym: str, ts: int, opens: list[dict]) -> dict | None:
    """A abertura mais recente do mesmo símbolo em/antes do fechamento."""
    best = None
    for o in opens:
        if (o.get("symbol") or "") != sym:
            continue
        try:
            ots = float(o.get("ts") or 0)
        except (TypeError, ValueError):
            ots = 0
        if ots <= ts and (best is None or ots >= float(best.get("ts") or 0)):
            best = o
    return best


def stats_by_dip_band(closed: list[dict], opens: list[dict],
                      edges=(0.03, 0.06, 0.10)) -> dict:
    """Agrupa o P&L por faixa de dip da entrada. Retorna {faixa: {count,pnl}}."""
    bands: dict[str, dict] = {}
    for c in closed:
        o = _match_open(c["symbol"], c["ts"], opens)
        if not o:
            continue
        try:
            dip = float(o.get("dip") or 0)
        except (TypeError, ValueError):
            continue
        label = _band_label(dip, edges)
        b = bands.setdefault(label, {"count": 0, "pnl": 0.0})
        b["count"] += 1
        b["pnl"] += c["pnl"]
    return bands


def _band_label(dip: float, edges) -> str:
    lo = 0.0
    for e in edges:
        if dip < e:
            return f"{lo * 100:.0f}-{e * 100:.0f}%"
        lo = e
    return f">{edges[-1] * 100:.0f}%"


def suggest_dip_min(closed: list[dict], opens: list[dict], cfg) -> float | None:
    """Sugere um dip_min melhor com base no histórico. None se faltar amostra.

    Regra conservadora: só sugere com >= autotune_min_trades fechados, e escolhe a
    menor faixa de dip cujo P&L acumulado seja positivo. Nunca sai dos limites
    [0.02, 0.10] para não virar algo extremo.
    """
    if len(closed) < cfg.autotune_min_trades:
        return None
    bands = stats_by_dip_band(closed, opens)
    edges = [0.02, 0.03, 0.04, 0.05, 0.06]
    melhor = None
    for label, b in bands.items():
        if b["pnl"] <= 0 or b["count"] < 3:
            continue
        try:
            lo = float(label.split("-")[0].replace("%", "")) / 100.0
        except (ValueError, IndexError):
            continue
        if melhor is None or lo < melhor:
            melhor = lo
    if melhor is None:
        return None
    return max(0.02, min(0.10, melhor))
