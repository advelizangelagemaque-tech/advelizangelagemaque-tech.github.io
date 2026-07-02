"""Painel web da subconta Bybit — ver posição ao vivo e ENCERRAR na mão.

Como a subconta de IA tem login restrito (só API), este painel é a sua janela
para a operação: mostra saldo, a posição aberta (entrada, atual, TP, SL), o
lucro/prejuízo em USDT, quanto falta para o TP, e um botão "Encerrar agora".

    python -m bybit_bot.panel --port 8080 --refresh 8

Acesse em http://SEU_IP:porta. IMPORTANTE: como tem botão que fecha posição
(mexe em dinheiro real), libere a porta na AWS SÓ para o seu IP.
"""

from __future__ import annotations

import argparse
import html
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import journal
from .config import BybitConfig
from .status import fetch_balance_usdt, fetch_open_positions
from .trader import close_position, make_client


def _pct_to_tp(entry: float, mark: float, tp: float) -> float:
    """Progresso do preço da entrada até o TP, em % (0 = na entrada, 100 = no TP)."""
    if not entry or not tp or tp == entry:
        return 0.0
    return max(0.0, min(100.0, (mark - entry) / (tp - entry) * 100.0))


def _fnum(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _position_card(p: dict) -> str:
    entry, mark = p["entry"], p["mark"]
    tp, sl = _fnum(p["tp"]), _fnum(p["sl"])
    pnl = p["pnl"]
    prog = _pct_to_tp(entry, mark, tp) if tp else 0.0
    cor_pnl = "#16a34a" if pnl >= 0 else "#dc2626"
    sinal = "+" if pnl >= 0 else ""
    falta_tp = ((tp - mark) / mark * 100.0) if (tp and mark) else 0.0
    falta_sl = ((mark - sl) / mark * 100.0) if (sl and mark) else 0.0
    sym = html.escape(p["symbol"])
    return f"""
    <div style="background:#fff;border:1px solid #e5e7eb;border-radius:14px;padding:18px 20px;margin:14px 0;box-shadow:0 1px 3px rgba(0,0,0,.06)">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
        <h3 style="margin:0;font-size:20px">{sym} <span style="color:#2563eb;font-size:14px">{html.escape((p['side'] or '').upper())}</span></h3>
        <div style="font-size:22px;font-weight:700;color:{cor_pnl}">{sinal}{pnl:.4f} USDT</div>
      </div>
      <table style="width:100%;border-collapse:collapse;margin:12px 0;font-size:15px">
        <tr><td style="padding:4px 0;color:#666">Entrada</td><td style="text-align:right">{entry:.8f}</td></tr>
        <tr><td style="padding:4px 0;color:#666">Preço atual</td><td style="text-align:right;font-weight:600">{mark:.8f}</td></tr>
        <tr><td style="padding:4px 0;color:#16a34a">🎯 Take Profit</td><td style="text-align:right;color:#16a34a">{tp:.8f} <small>(falta {falta_tp:+.2f}%)</small></td></tr>
        <tr><td style="padding:4px 0;color:#dc2626">🛑 Stop Loss</td><td style="text-align:right;color:#dc2626">{sl:.8f} <small>(a {falta_sl:.2f}% abaixo)</small></td></tr>
      </table>
      <div style="background:#eef2ff;border-radius:8px;overflow:hidden;height:22px;margin:6px 0 4px">
        <div style="width:{prog:.0f}%;height:100%;background:linear-gradient(90deg,#3b82f6,#16a34a);
             display:flex;align-items:center;justify-content:center;color:#fff;font-size:12px;font-weight:600">
          {prog:.0f}% até o TP</div>
      </div>
      <form method="POST" action="/close" onsubmit="return confirm('Encerrar AGORA a posição {sym} a mercado?')" style="margin-top:14px">
        <input type="hidden" name="symbol" value="{sym}">
        <button type="submit" style="width:100%;background:#111827;color:#fff;border:0;border-radius:10px;
                padding:12px;font-size:16px;font-weight:600;cursor:pointer">⏹ Encerrar agora</button>
      </form>
    </div>"""


def _stats_card(ex, cfg) -> str:
    """Card de desempenho (aprendizado): win rate, expectativa, melhores faixas."""
    closed = journal.fetch_closed(ex)
    st = journal.compute_stats(closed)
    if st["count"] == 0:
        return ('<div style="background:#fff;border:1px solid #e5e7eb;border-radius:14px;'
                'padding:16px 20px;margin:14px 0;color:#888">📊 Ainda sem operações fechadas '
                'para gerar estatísticas.</div>')
    cor = "#16a34a" if st["total_pnl"] >= 0 else "#dc2626"
    pf = "∞" if st["profit_factor"] == float("inf") else f"{st['profit_factor']:.2f}"
    bands = journal.stats_by_dip_band(closed, journal.load_opens())
    linhas = ""
    for label, b in sorted(bands.items()):
        bcor = "#16a34a" if b["pnl"] >= 0 else "#dc2626"
        linhas += (f'<tr><td style="padding:2px 0">dip {label}</td>'
                   f'<td style="text-align:right">{b["count"]}x</td>'
                   f'<td style="text-align:right;color:{bcor}">{b["pnl"]:+.3f}</td></tr>')
    tabela = (f'<table style="width:100%;font-size:13px;margin-top:8px;color:#555">'
              f'<tr style="color:#999"><td>faixa de dip</td><td style="text-align:right">trades</td>'
              f'<td style="text-align:right">P&L</td></tr>{linhas}</table>') if bands else ""
    sug = journal.suggest_dip_min(closed, journal.load_opens(), cfg)
    sug_txt = ""
    if sug and abs(sug - cfg.dip_min) >= 0.005:
        estado = "aplicado" if cfg.autotune else "sugestão (autotune desligado)"
        sug_txt = (f'<div style="margin-top:8px;font-size:13px;color:#7c3aed">💡 dip_min ideal '
                   f'≈ {sug * 100:.0f}% — {estado}.</div>')
    return f"""
    <div style="background:#fff;border:1px solid #e5e7eb;border-radius:14px;padding:16px 20px;margin:14px 0">
      <h3 style="margin:0 0 10px">📊 Desempenho (aprendizado)</h3>
      <div style="display:flex;flex-wrap:wrap;gap:14px">
        <div><div style="font-size:22px;font-weight:700">{st['count']}</div><div style="font-size:12px;color:#888">trades</div></div>
        <div><div style="font-size:22px;font-weight:700">{st['win_rate'] * 100:.0f}%</div><div style="font-size:12px;color:#888">acerto</div></div>
        <div><div style="font-size:22px;font-weight:700;color:{cor}">{st['total_pnl']:+.3f}</div><div style="font-size:12px;color:#888">P&L USDT</div></div>
        <div><div style="font-size:22px;font-weight:700">{st['expectancy']:+.3f}</div><div style="font-size:12px;color:#888">média/trade</div></div>
        <div><div style="font-size:22px;font-weight:700">{pf}</div><div style="font-size:12px;color:#888">profit factor</div></div>
      </div>
      {tabela}{sug_txt}
    </div>"""


def render_page(refresh: int) -> str:
    cfg = BybitConfig.load()
    cfg.require_keys()
    ex = make_client(cfg)
    total, free = fetch_balance_usdt(ex)
    positions = fetch_open_positions(ex)
    env = "TESTNET" if cfg.use_testnet else "REAL"

    stats_html = _stats_card(ex, cfg)
    if positions:
        corpo = "".join(_position_card(p) for p in positions)
    else:
        corpo = ('<div style="background:#fff;border:1px solid #e5e7eb;border-radius:14px;'
                 'padding:24px;text-align:center;color:#888">Nenhuma posição aberta agora. '
                 'O agente abre a próxima quando achar um token em alta com dip.</div>')

    return f"""<!doctype html><html lang="pt-br"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="{refresh}">
<title>Bybit — Painel do Agente</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;background:#f7f8fa;margin:0;padding:20px;color:#1f2937}}
.wrap{{max-width:560px;margin:auto}}</style></head>
<body><div class="wrap">
  <h1 style="color:#0b3d91;margin:0 0 4px">🤖 Agente Bybit</h1>
  <div style="color:#6b7280;font-size:13px;margin-bottom:14px">Conta {env} · atualiza a cada {refresh}s</div>
  <div style="background:#111827;color:#fff;border-radius:14px;padding:16px 20px;margin-bottom:8px">
    <div style="font-size:13px;opacity:.8">Saldo da subconta</div>
    <div style="font-size:26px;font-weight:700">{total:.2f} USDT <span style="font-size:14px;opacity:.7">(livre {free:.2f})</span></div>
  </div>
  {stats_html}
  {corpo}
  <div style="color:#9ca3af;font-size:12px;text-align:center;margin-top:18px">
    TP/SL ficam na Bybit — a posição fecha sozinha mesmo se o painel estiver fora do ar.
  </div>
</div></body></html>"""


def _result_page(title: str, body: str, color: str) -> str:
    return f"""<!doctype html><html lang="pt-br"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bybit — Painel</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;background:#f7f8fa;padding:40px}}
.box{{background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:24px;max-width:560px;margin:auto}}
a{{color:#0b3d91}}</style></head><body><div class="box">
<h2 style="color:{color};margin-top:0">{title}</h2><p style="word-break:break-all">{body}</p>
<p><a href="/">← voltar ao painel</a></p></div></body></html>"""


class _Handler(BaseHTTPRequestHandler):
    refresh = 8

    def do_GET(self):  # noqa: N802
        if self.path.startswith("/health"):
            return self._send(200, "ok", "text/plain")
        try:
            page = render_page(self.refresh)
        except Exception as exc:  # noqa: BLE001
            page = _result_page("Erro ao ler a conta", html.escape(str(exc)), "#dc2626")
        self._send(200, page, "text/html; charset=utf-8")

    def do_POST(self):  # noqa: N802
        if not self.path.startswith("/close"):
            return self._send(404, "not found", "text/plain")
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        symbol = (urllib.parse.parse_qs(body).get("symbol") or [""])[0].strip()
        if not symbol:
            return self._send(400, _result_page("Faltou o símbolo", "Informe o par.", "#dc2626"),
                              "text/html; charset=utf-8")
        try:
            cfg = BybitConfig.load()
            cfg.require_keys()
            ex = make_client(cfg)
            res = close_position(ex, symbol)
        except Exception as exc:  # noqa: BLE001
            return self._send(200, _result_page("❌ Falha ao encerrar", html.escape(str(exc)),
                                                "#dc2626"), "text/html; charset=utf-8")
        if res["closed"] == 0:
            msg = f"Nenhuma posição aberta em {html.escape(symbol)} (já pode ter fechado)."
            return self._send(200, _result_page("Nada a encerrar", msg, "#6b7280"),
                              "text/html; charset=utf-8")
        return self._send(200, _result_page("✅ Posição encerrada!",
                          f"{html.escape(symbol)} — {res['closed']} contratos fechados a mercado. "
                          f"Ordem: {html.escape(str(res['order_id']))}", "#16a34a"),
                          "text/html; charset=utf-8")

    def _send(self, code: int, body: str, ctype: str):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description="Painel web da Bybit (ver + encerrar)")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--refresh", type=int, default=8, help="Segundos entre atualizações.")
    args = ap.parse_args()

    _Handler.refresh = args.refresh
    server = ThreadingHTTPServer((args.host, args.port), _Handler)
    print(f"Painel Bybit no ar em http://{args.host}:{args.port} (atualiza a cada {args.refresh}s). "
          "Ctrl+C para parar.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nPainel encerrado.")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
