"""Painel web ao vivo do sniper (servidor embutido, sem dependências extras).

- GET  /         -> dashboard (estatísticas + PnL + operações), com auto-refresh
                    e um formulário de VENDA manual de token pump.fun.
- POST /sell     -> vende 100% do token informado (usa a carteira-isca).
- GET  /health   -> "ok".

Uso:
    python -m sniper.webpanel --port 8080 --csv trades.csv --refresh 10

Acesse em http://SEU_IP:porta. Na AWS, mantenha a porta liberada SÓ para o seu
IP (o botão de venda é uma ação que mexe na carteira).
"""

from __future__ import annotations

import argparse
import csv
import html
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .dashboard import build_html

SOL_JOURNAL = "sol_trades.csv"


def _open_positions(sol_csv: str = SOL_JOURNAL) -> list[str]:
    """Tokens comprados e ainda não vendidos (BUY sem SELL correspondente)."""
    try:
        with open(sol_csv, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except FileNotFoundError:
        return []
    open_mints: list[str] = []
    for r in rows:
        mint = (r.get("mint") or "").strip()
        event = (r.get("event") or "").upper()
        if not mint:
            continue
        if event == "BUY":
            open_mints.append(mint)
        elif event == "SELL" and mint in open_mints:
            open_mints.remove(mint)
    return open_mints


def _open_positions_html(sol_csv: str = SOL_JOURNAL) -> str:
    mints = _open_positions(sol_csv)
    if not mints:
        return ('<div style="background:#fff;border:1px solid #e5e7eb;border-radius:12px;'
                'padding:14px 18px;margin:18px 0"><h3 style="margin:0 0 6px">📌 Posições abertas</h3>'
                '<div style="color:#888">Nenhuma posição aberta.</div></div>')
    botoes = ""
    for m in mints:
        short = html.escape(m[:6] + "…" + m[-4:])
        botoes += (
            f'<div style="display:inline-flex;gap:4px;margin:4px;align-items:center">'
            f'<form method="POST" action="/sell" onsubmit="return confirm(\'Vender 100% de {short}?\')" style="margin:0">'
            f'<input type="hidden" name="mint" value="{html.escape(m)}">'
            f'<button type="submit" style="background:#c0392b;color:#fff;border:0;border-radius:8px 0 0 8px;'
            f'padding:8px 14px;font-weight:600;cursor:pointer">Vender {short}</button></form>'
            f'<form method="POST" action="/dismiss" onsubmit="return confirm(\'Dispensar {short} como perda? (para tokens que não dá para vender)\')" style="margin:0">'
            f'<input type="hidden" name="mint" value="{html.escape(m)}">'
            f'<button type="submit" title="Token ilíquido — marca como perda e remove"'
            f' style="background:#8a8f98;color:#fff;border:0;border-radius:0 8px 8px 0;'
            f'padding:8px 12px;cursor:pointer">Dispensar</button></form></div>')
    return ('<div style="background:#fff;border:1px solid #e5e7eb;border-radius:12px;'
            'padding:14px 18px;margin:18px 0"><h3 style="margin:0 0 6px">📌 Posições abertas</h3>'
            f'<div>{botoes}</div></div>')

_EMPTY = """<!doctype html><html lang="pt-br"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="{refresh}">
<title>Sniper Bot — Painel</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;background:#f7f8fa;color:#444;
padding:40px;text-align:center}}</style></head>
<body><h1 style="color:#0b3d91">Sniper Bot — Painel</h1>
{sellform}
<p>Ainda sem operações no <code>{csv}</code>.</p>
<p>O bot está de tocaia. Esta página atualiza sozinha a cada {refresh}s.</p>
</body></html>"""

_SELL_FORM = """
<div style="background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:14px 18px;margin:18px 0">
  <h3 style="margin:0 0 8px">🔴 Venda manual (pump.fun)</h3>
  <form method="POST" action="/sell" onsubmit="return confirm('Vender 100% deste token?')"
        style="display:flex;gap:8px;flex-wrap:wrap">
    <input name="mint" placeholder="Endereço do token (mint)" required
           style="flex:1;min-width:280px;padding:8px 10px;border:1px solid #ccc;border-radius:8px">
    <button type="submit"
            style="background:#c0392b;color:#fff;border:0;border-radius:8px;padding:8px 18px;font-weight:600;cursor:pointer">
      Vender 100%</button>
  </form>
  <div style="font-size:12px;color:#888;margin-top:6px">Vende todos os tokens desse endereço que estiverem na carteira-isca.</div>
</div>"""


def _result_page(title: str, body: str, color: str) -> str:
    return f"""<!doctype html><html lang="pt-br"><head><meta charset="utf-8">
<title>Sniper Bot — Venda</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;background:#f7f8fa;padding:40px}}
.box{{background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:24px;max-width:760px;margin:auto}}
a{{color:#0b3d91}}</style></head>
<body><div class="box"><h2 style="color:{color};margin-top:0">{title}</h2>
<p style="word-break:break-all">{body}</p>
<p><a href="/">← voltar ao painel</a></p></div></body></html>"""


def _record_sell(mint: str, signature: str) -> None:
    """Registra a venda manual no mesmo CSV do autopilot, para aparecer no painel."""
    try:
        from solana_sniper.pumpsnipe import _record
        _record("SELL", mint, reason="venda manual (painel)", signature=signature)
    except Exception:  # noqa: BLE001
        pass


def _buy_sol_of(mint: str, sol_csv: str = SOL_JOURNAL) -> float:
    """Quanto SOL foi gasto comprando esse token (para contabilizar a perda)."""
    try:
        with open(sol_csv, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if (r.get("mint") or "").strip() == mint and (r.get("event") or "").upper() == "BUY":
                    return float(r.get("sol") or 0)
    except FileNotFoundError:
        pass
    return 0.0


def _dismiss(mint: str) -> None:
    """Marca a posição como perda (token ilíquido) e a remove das abertas."""
    from solana_sniper.pumpsnipe import _record
    loss = _buy_sol_of(mint)
    _record("SELL", mint, pnl_sol=f"{-loss:.6f}", reason="ilíquido (dispensado)")


class _Handler(BaseHTTPRequestHandler):
    csv_path = "trades.csv"
    refresh = 10

    # ---- GET ----
    def do_GET(self):  # noqa: N802
        if self.path.startswith("/health"):
            return self._send(200, "ok", "text/plain")
        top = _open_positions_html() + _SELL_FORM
        try:
            page = build_html(self.csv_path, refresh=self.refresh)
            page = page.replace("<body>", "<body>\n" + top, 1)
        except FileNotFoundError:
            page = _EMPTY.format(refresh=self.refresh, csv=html.escape(self.csv_path),
                                 sellform=top)
        self._send(200, page, "text/html; charset=utf-8")

    # ---- POST /sell e /dismiss ----
    def do_POST(self):  # noqa: N802
        is_sell = self.path.startswith("/sell")
        is_dismiss = self.path.startswith("/dismiss")
        if not (is_sell or is_dismiss):
            return self._send(404, "not found", "text/plain")
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        mint = (urllib.parse.parse_qs(body).get("mint") or [""])[0].strip()
        if not mint:
            return self._send(400, _result_page("Faltou o token", "Informe o endereço (mint).",
                                                "#c0392b"), "text/html; charset=utf-8")
        if is_dismiss:
            _dismiss(mint)
            return self._send(200, _result_page("✅ Dispensado",
                              f"{html.escape(mint)} foi marcado como perda e removido das posições abertas.",
                              "#5f6368"), "text/html; charset=utf-8")
        try:
            sig = self._sell(mint)
        except Exception as exc:  # noqa: BLE001
            return self._send(200, _result_page("❌ Falha na venda", html.escape(str(exc)),
                                                "#c0392b"), "text/html; charset=utf-8")
        _record_sell(mint, sig)
        link = f'<a href="https://solscan.io/tx/{sig}" target="_blank">{sig}</a>'
        return self._send(200, _result_page("✅ Venda enviada!",
                          f"Token {html.escape(mint)} vendido.<br>Assinatura: {link}", "#34a853"),
                          "text/html; charset=utf-8")

    def _sell(self, mint: str) -> str:
        from solana_sniper.config import SolConfig
        from solana_sniper.pumpfun import sell_any
        from solana_sniper.rpc import SolanaRPC
        from solana_sniper.wallet import load_burner
        cfg = SolConfig.load()
        rpc = SolanaRPC(cfg.rpc_url)
        wallet = load_burner(cfg.keypair_path)
        res = sell_any(rpc, wallet, cfg, mint, send_it=True)
        return str(res.get("signature") or "")

    # ---- util ----
    def _send(self, code: int, body: str, ctype: str):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):  # silencia o log de acesso padrão
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description="Painel web do sniper")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--csv", default="trades.csv")
    ap.add_argument("--refresh", type=int, default=10, help="Segundos entre atualizações.")
    args = ap.parse_args()

    _Handler.csv_path = args.csv
    _Handler.refresh = args.refresh
    server = ThreadingHTTPServer((args.host, args.port), _Handler)
    print(f"Painel no ar em http://{args.host}:{args.port}  (lendo {args.csv}, "
          f"atualiza a cada {args.refresh}s). Ctrl+C para parar.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nPainel encerrado.")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
