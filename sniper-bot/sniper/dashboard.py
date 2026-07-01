"""Gera um dashboard HTML (offline) a partir do diário trades.csv.

Mostra estatísticas (win rate, PnL, profit factor) e uma curva de PnL
acumulado desenhada como SVG embutido — não depende de internet nem libs JS.

Uso:
    python -m sniper.dashboard                      # lê trades.csv -> dashboard.html
    python -m sniper.dashboard trades.csv -o x.html
"""

from __future__ import annotations

import argparse
import csv
import html

from .summary import summarize


def _closed_pnls(path: str) -> list[tuple[str, float]]:
    """Lista (símbolo, pnl) das operações fechadas, na ordem do arquivo."""
    out: list[tuple[str, float]] = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if (row.get("status") or "").upper() in {"WIN", "LOSS"}:
                out.append((row.get("symbol", "?"), float(row.get("pnl_usdt") or 0)))
    return out


def _pnl_curve_svg(pnls: list[float], w: int = 720, h: int = 240, pad: int = 30) -> str:
    """Desenha a curva de PnL acumulado como SVG (sem dependências)."""
    if not pnls:
        return '<p class="muted">Sem operações fechadas ainda — rode em --paper para gerar dados.</p>'

    cum, total = [], 0.0
    for p in pnls:
        total += p
        cum.append(total)

    lo, hi = min(0.0, min(cum)), max(0.0, max(cum))
    span = (hi - lo) or 1.0
    n = len(cum)
    dx = (w - 2 * pad) / max(n - 1, 1)

    def x(i): return pad + i * dx
    def y(v): return h - pad - (v - lo) / span * (h - 2 * pad)

    pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(cum))
    zero_y = y(0.0)
    last_color = "#34a853" if cum[-1] >= 0 else "#c0392b"
    area = f"{x(0):.1f},{zero_y:.1f} " + pts + f" {x(n - 1):.1f},{zero_y:.1f}"

    return f'''<svg viewBox="0 0 {w} {h}" width="100%" preserveAspectRatio="xMidYMid meet">
  <line x1="{pad}" y1="{zero_y:.1f}" x2="{w - pad}" y2="{zero_y:.1f}" stroke="#ccc" stroke-dasharray="4 4"/>
  <polygon points="{area}" fill="{last_color}" fill-opacity="0.10"/>
  <polyline points="{pts}" fill="none" stroke="{last_color}" stroke-width="2.5"/>
  <text x="{pad}" y="16" font-size="12" fill="#666">PnL acumulado (USDT)</text>
  <text x="{w - pad}" y="{y(cum[-1]) - 8:.1f}" font-size="13" font-weight="700"
        fill="{last_color}" text-anchor="end">{cum[-1]:+.2f}</text>
</svg>'''


def _stat_card(label: str, value: str, color: str = "#1a1a1a") -> str:
    return (f'<div class="card"><div class="cval" style="color:{color}">{value}</div>'
            f'<div class="clabel">{html.escape(label)}</div></div>')


def _sol_section(sol_csv: str) -> str:
    """Seção do painel com as operações da Solana (pump.fun), se houver."""
    try:
        with open(sol_csv, newline="", encoding="utf-8") as f:
            ops = list(csv.DictReader(f))
    except FileNotFoundError:
        return ""
    if not ops:
        return ""

    sells = [o for o in ops if (o.get("event") or "").upper() == "SELL"]
    buys = [o for o in ops if (o.get("event") or "").upper() == "BUY"]
    total = sum(float(o.get("pnl_sol") or 0) for o in sells)
    color = "#34a853" if total >= 0 else "#c0392b"

    rows = ""
    for o in reversed(ops[-15:]):
        ev = (o.get("event") or "").upper()
        mint = html.escape((o.get("mint") or "")[:8] + "…")
        if ev == "SELL":
            p = float(o.get("pnl_sol") or 0)
            c = "#34a853" if p >= 0 else "#c0392b"
            val = f'<span style="color:{c}">{p:+.4f} SOL</span> <span class="muted">({html.escape(o.get("reason") or "")})</span>'
        else:
            val = f'<span class="muted">comprou {html.escape(o.get("sol") or "")} SOL</span>'
        rows += f'<tr><td>{ev}</td><td>{mint}</td><td style="text-align:right">{val}</td></tr>'

    return f'''
  <div class="cards">
    {_stat_card("Compras (Solana)", str(len(buys)))}
    {_stat_card("Vendas (Solana)", str(len(sells)))}
    {_stat_card("PnL Solana (SOL)", f"{total:+.4f}", color)}
  </div>
  <div class="panel">
    <h3 style="margin:0 0 8px">🟣 Operações Solana (pump.fun)</h3>
    <table><thead><tr><th>Evento</th><th>Token</th><th style="text-align:right">Resultado</th></tr></thead>
    <tbody>{rows}</tbody></table>
  </div>'''


def build_html(path: str, refresh: int = 0, sol_csv: str = "sol_trades.csv") -> str:
    s = summarize(path)
    pairs = _closed_pnls(path)
    pnls = [p for _, p in pairs]
    meta_refresh = f'<meta http-equiv="refresh" content="{refresh}">' if refresh else ""

    pf = "∞" if s["profit_factor"] == float("inf") else f"{s['profit_factor']:.2f}"
    pnl_color = "#34a853" if s["total_pnl"] >= 0 else "#c0392b"
    cards = "".join([
        _stat_card("Trades fechados", str(s["closed"])),
        _stat_card("Taxa de acerto", f"{s['win_rate']:.1%}"),
        _stat_card("PnL total (USDT)", f"{s['total_pnl']:+.2f}", pnl_color),
        _stat_card("Expectativa/trade", f"{s['expectancy']:+.2f}",
                   "#34a853" if s["expectancy"] >= 0 else "#c0392b"),
        _stat_card("Profit factor", pf),
        _stat_card("Pulados (filtro)", str(s["skipped"])),
    ])

    rows = ""
    for sym, p in reversed(pairs[-20:]):  # últimas 20, mais recentes no topo
        c = "#34a853" if p >= 0 else "#c0392b"
        rows += (f'<tr><td>{html.escape(sym)}</td>'
                 f'<td style="color:{c};text-align:right">{p:+.4f}</td></tr>')
    if not rows:
        rows = '<tr><td colspan="2" class="muted">Nenhuma operação fechada.</td></tr>'

    return f'''<!doctype html>
<html lang="pt-br"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{meta_refresh}
<title>Sniper Bot — Dashboard</title>
<style>
  body{{font-family:Segoe UI,Arial,sans-serif;background:#f7f8fa;color:#1a1a1a;margin:0;padding:24px}}
  h1{{color:#0b3d91;font-size:22px;margin:0 0 4px}}
  .muted{{color:#999}}
  .cards{{display:flex;flex-wrap:wrap;gap:12px;margin:18px 0}}
  .card{{background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:14px 18px;min-width:130px;flex:1}}
  .cval{{font-size:24px;font-weight:700}}
  .clabel{{font-size:12px;color:#666;margin-top:4px}}
  .panel{{background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:16px;margin-bottom:18px}}
  table{{width:100%;border-collapse:collapse;font-size:14px}}
  th,td{{padding:8px 10px;border-bottom:1px solid #f0f0f0}}
  th{{text-align:left;color:#666;font-weight:600}}
</style></head>
<body>
  <h1>Sniper Bot — Dashboard</h1>
  <div class="muted">Gerado a partir de <code>{html.escape(path)}</code></div>
  <div class="cards">{cards}</div>
  <div class="panel">{_pnl_curve_svg(pnls)}</div>
  <div class="panel">
    <h3 style="margin:0 0 8px">Últimas operações (Binance)</h3>
    <table><thead><tr><th>Símbolo</th><th style="text-align:right">PnL (USDT)</th></tr></thead>
    <tbody>{rows}</tbody></table>
  </div>
  {_sol_section(sol_csv)}
</body></html>'''


def main() -> int:
    ap = argparse.ArgumentParser(description="Gera dashboard HTML do diário")
    ap.add_argument("csv", nargs="?", default="trades.csv")
    ap.add_argument("-o", "--out", default="dashboard.html")
    args = ap.parse_args()
    try:
        page = build_html(args.csv)
    except FileNotFoundError:
        print(f"Diário não encontrado: {args.csv}. Rode o bot em --paper primeiro.")
        return 1
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"Dashboard gerado: {args.out}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
