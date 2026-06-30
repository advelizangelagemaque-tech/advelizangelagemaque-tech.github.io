"""Painel web ao vivo do sniper (servidor embutido, sem dependências extras).

Serve o dashboard (estatísticas + curva de PnL + últimas operações) lendo o
trades.csv a cada acesso e atualizando sozinho no navegador.

Uso:
    python -m sniper.webpanel                 # porta 8080, lê trades.csv
    python -m sniper.webpanel --port 8080 --csv trades.csv --refresh 10

Acesse em http://SEU_IP:porta  (na AWS, libere a porta no security group,
de preferência só para o seu IP).
"""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .dashboard import build_html

_EMPTY = """<!doctype html><html lang="pt-br"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="{refresh}">
<title>Sniper Bot — Painel</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;background:#f7f8fa;color:#444;
padding:40px;text-align:center}}</style></head>
<body><h1 style="color:#0b3d91">Sniper Bot — Painel</h1>
<p>Ainda sem operações no <code>{csv}</code>.</p>
<p class="muted">O bot está de tocaia. Esta página atualiza sozinha a cada {refresh}s.</p>
</body></html>"""


class _Handler(BaseHTTPRequestHandler):
    csv_path = "trades.csv"
    refresh = 10

    def do_GET(self):  # noqa: N802
        if self.path.startswith("/health"):
            return self._send(200, "ok", "text/plain")
        try:
            page = build_html(self.csv_path, refresh=self.refresh)
        except FileNotFoundError:
            page = _EMPTY.format(refresh=self.refresh, csv=self.csv_path)
        self._send(200, page, "text/html; charset=utf-8")

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
