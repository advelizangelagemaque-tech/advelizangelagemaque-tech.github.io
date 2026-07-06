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
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import brain, journal
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


def _stats_card(ex, cfg, closed=None, opens=None) -> str:
    """Card de desempenho (aprendizado): win rate, expectativa, melhores faixas."""
    if closed is None:
        closed = journal.fetch_closed(ex)
    if opens is None:
        opens = journal.load_opens()
    st = journal.compute_stats(closed)
    if st["count"] == 0:
        return ('<div style="background:#fff;border:1px solid #e5e7eb;border-radius:14px;'
                'padding:16px 20px;margin:14px 0;color:#888">📊 Ainda sem operações fechadas '
                'para gerar estatísticas.</div>')
    cor = "#16a34a" if st["total_pnl"] >= 0 else "#dc2626"
    pf = "∞" if st["profit_factor"] == float("inf") else f"{st['profit_factor']:.2f}"
    bands = journal.stats_by_dip_band(closed, opens)
    linhas = ""
    for label, b in sorted(bands.items()):
        bcor = "#16a34a" if b["pnl"] >= 0 else "#dc2626"
        linhas += (f'<tr><td style="padding:2px 0">dip {label}</td>'
                   f'<td style="text-align:right">{b["count"]}x</td>'
                   f'<td style="text-align:right;color:{bcor}">{b["pnl"]:+.3f}</td></tr>')
    tabela = (f'<table style="width:100%;font-size:13px;margin-top:8px;color:#555">'
              f'<tr style="color:#999"><td>faixa de dip</td><td style="text-align:right">trades</td>'
              f'<td style="text-align:right">P&L</td></tr>{linhas}</table>') if bands else ""
    sug = journal.suggest_dip_min(closed, opens, cfg)
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


_BR_TZ = timezone(timedelta(hours=-3))   # horário de Brasília (sem horário de verão)


def _fmt_time(ts_ms: int) -> str:
    if not ts_ms:
        return "-"
    try:
        return datetime.fromtimestamp(ts_ms / 1000, _BR_TZ).strftime("%d/%m %H:%M")
    except (ValueError, OSError):
        return "-"


def _history_card(ex, closed=None, opens=None) -> str:
    """Histórico de TODAS as operações fechadas (mais recente no topo)."""
    if closed is None:
        closed = journal.fetch_closed(ex, limit=100)
    if opens is None:
        opens = journal.load_opens()
    if not closed:
        return ('<div style="background:#fff;border:1px solid #e5e7eb;border-radius:14px;'
                'padding:16px 20px;margin:14px 0;color:#888">📜 Ainda sem operações fechadas '
                'no histórico.</div>')
    linhas = ""
    for c in reversed(closed):
        tipo = journal.classify_exit(c, opens)
        cor = "#16a34a" if c["pnl"] >= 0 else "#dc2626"
        badge = "#16a34a" if tipo == "TP" else "#dc2626"
        sym = html.escape((c["symbol"] or "?").replace("/USDT:USDT", ""))
        linhas += (
            f'<tr style="border-top:1px solid #f0f0f0">'
            f'<td style="padding:6px 4px;color:#666;white-space:nowrap">{_fmt_time(c["ts"])}</td>'
            f'<td style="padding:6px 4px;font-weight:600">{sym}</td>'
            f'<td style="padding:6px 4px"><span style="background:{badge};color:#fff;'
            f'border-radius:6px;padding:1px 7px;font-size:12px">{tipo}</span></td>'
            f'<td style="padding:6px 4px;text-align:right;color:{cor};font-weight:600">'
            f'{c["pnl"]:+.4f}</td></tr>')
    total_pnl = sum(c["pnl"] for c in closed)
    cor_total = "#16a34a" if total_pnl >= 0 else "#dc2626"
    return f"""
    <div style="background:#fff;border:1px solid #e5e7eb;border-radius:14px;padding:16px 20px;margin:14px 0">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <h3 style="margin:0">📜 Histórico ({len(closed)})</h3>
        <div style="font-weight:700;color:{cor_total}">Total {total_pnl:+.4f} USDT</div>
      </div>
      <div style="max-height:360px;overflow-y:auto;margin-top:8px">
        <table style="width:100%;border-collapse:collapse;font-size:14px">
          <tr style="color:#999;text-align:left;font-size:12px">
            <th style="padding:2px 4px">data</th><th style="padding:2px 4px">par</th>
            <th style="padding:2px 4px">saída</th><th style="padding:2px 4px;text-align:right">P&L</th></tr>
          {linhas}
        </table>
      </div>
      <div style="font-size:11px;color:#aaa;margin-top:6px">Horário de Brasília. Últimas 100 operações.</div>
    </div>"""


def _brain_card(cfg, closed) -> str:
    """Mostra o estado atual do cérebro: margem em uso, PF recente e situação."""
    if not getattr(cfg, "brain_enabled", False):
        return ""
    recent = [c["pnl"] for c in closed][-cfg.brain_window:]
    dec = brain.decide(recent, cfg)
    pf = brain.rolling_pf(recent) if recent else 1.0
    pf_txt = "∞" if pf == float("inf") else f"{pf:.2f}"
    margem = cfg.margin_usdt * dec["margin_mult"]

    if dec["margin_mult"] == 0.0:
        cor, emoji, estado = "#dc2626", "⏸", "PAUSADO (defensivo)"
    elif dec["margin_mult"] < 1.0:
        cor, emoji, estado = "#d97706", "🟡", "Freio de mão (risco reduzido)"
    else:
        cor, emoji, estado = "#16a34a", "🟢", "Normal (força total)"

    return f"""
    <div style="background:#fff;border:1px solid #e5e7eb;border-radius:14px;padding:16px 20px;margin:14px 0;border-left:5px solid {cor}">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px">
        <h3 style="margin:0">🧠 Cérebro</h3>
        <div style="font-weight:700;color:{cor}">{emoji} {estado}</div>
      </div>
      <div style="display:flex;flex-wrap:wrap;gap:18px;margin-top:10px">
        <div><div style="font-size:22px;font-weight:700;color:{cor}">{margem:.0f} USDT</div>
             <div style="font-size:12px;color:#888">margem por trade agora</div></div>
        <div><div style="font-size:22px;font-weight:700">{pf_txt}</div>
             <div style="font-size:12px;color:#888">PF recente (últ. {len(recent)})</div></div>
        <div><div style="font-size:22px;font-weight:700">{cfg.margin_usdt:.0f} USDT</div>
             <div style="font-size:12px;color:#888">margem cheia (quando PF&gt;1)</div></div>
      </div>
      <div style="font-size:12px;color:#888;margin-top:8px">Volta pra {cfg.margin_usdt:.0f} USDT sozinho quando o PF recente passar de 1.</div>
    </div>"""


def _launch_section() -> str:
    """Seção do observador de lançamentos: quantos pegou + retorno médio por minuto."""
    from . import launch as launch_mod
    rows = launch_mod.load_obs()
    if not rows:
        return ('<hr style="border:0;border-top:2px solid #e5e7eb;margin:28px 0 8px">'
                '<h2 style="color:#0891b2;margin:0 0 4px">🚀 Observador de Lançamentos</h2>'
                '<div style="background:#ecfeff;border:1px dashed #67e8f9;border-radius:14px;'
                'padding:16px 20px;margin:8px 0;color:#0e7490">Ligado e de tocaia — ainda nenhum '
                'lançamento novo detectado. Assim que a Bybit listar um perp novo, aparece aqui.</div>')
    resumo, n_sym = launch_mod.summarize(rows)
    linhas = ""
    for cp in launch_mod.CHECKPOINTS:
        if cp in resumo:
            r = resumo[cp]
            cor = "#16a34a" if r["media"] >= 0 else "#dc2626"
            linhas += (f'<tr style="border-top:1px solid #f0f0f0">'
                       f'<td style="padding:5px 4px">{cp} min</td>'
                       f'<td style="padding:5px 4px;text-align:right">{r["n"]}</td>'
                       f'<td style="padding:5px 4px;text-align:right;color:{cor};font-weight:600">'
                       f'{r["media"] * 100:+.1f}%</td>'
                       f'<td style="padding:5px 4px;text-align:right">{r["pct_up"] * 100:.0f}%</td></tr>')
    return f"""
    <hr style="border:0;border-top:2px solid #e5e7eb;margin:28px 0 8px">
    <h2 style="color:#0891b2;margin:0 0 4px">🚀 Observador de Lançamentos <span style="font-size:13px;color:#888">({n_sym} pegos)</span></h2>
    <div style="background:#fff;border:1px solid #e5e7eb;border-radius:14px;padding:14px 18px;margin:8px 0">
      <table style="width:100%;border-collapse:collapse;font-size:14px">
        <tr style="color:#999;text-align:left;font-size:12px">
          <th style="padding:2px 4px">após listar</th><th style="padding:2px 4px;text-align:right">nº</th>
          <th style="padding:2px 4px;text-align:right">retorno médio</th>
          <th style="padding:2px 4px;text-align:right">% subiu</th></tr>
        {linhas}
      </table>
      <div style="font-size:12px;color:#0e7490;margin-top:8px">Retorno médio <b>positivo</b> = comprar tende a valer · <b>negativo</b> = fadar (short). Sem dinheiro ainda — só coletando dado.</div>
    </div>"""


def _equity_chart(path: str = "delta_equity.csv") -> str:
    """Gráfico do LUCRO/PREJUÍZO REAL no tempo (saldo menos o que você depositou).

    Descontar os aportes é o que impede o erro clássico: sem isso, um depósito
    faz o saldo pular e PARECE lucro. Aqui saldo e depósito sobem juntos e se
    cancelam — sobra só o ganho/perda de verdade.
    """
    try:
        with open(path, encoding="utf-8") as f:
            pts = []
            for line in f:
                parts = line.strip().split(",")
                if len(parts) == 2:
                    pts.append((int(parts[0]), float(parts[1])))
    except (FileNotFoundError, ValueError):
        pts = []
    if len(pts) < 3:
        return ('<div style="color:#9ca3af;font-size:13px;margin:8px 0">📈 Gráfico: '
                'coletando dados… (aparece após alguns minutos rodando).</div>')
    # desconta os aportes: lucro_real(t) = saldo(t) - total depositado até t
    from . import delta as delta_mod
    timeline = delta_mod.deposits_timeline()
    if timeline:
        def _dep_asof(t: int) -> float:
            return sum(a for (dt, a) in timeline if dt <= t)
        pts = [(t, v - _dep_asof(t)) for (t, v) in pts]
        titulo = "📈 Lucro/prejuízo real no tempo"
    else:
        titulo = "📈 Saldo do Delta no tempo (registre aportes p/ ver o lucro real)"
    # downsample para ~100 pontos
    if len(pts) > 100:
        step = len(pts) // 100
        pts = pts[::step]
    ys = [v for _, v in pts]
    lo, hi = min(ys), max(ys)
    rng = (hi - lo) or 1.0
    w, h, pad = 520, 120, 6
    n = len(pts)
    coords = []
    for i, (_, v) in enumerate(pts):
        x = pad + i * (w - 2 * pad) / (n - 1)
        y = pad + (h - 2 * pad) * (1 - (v - lo) / rng)
        coords.append(f"{x:.1f},{y:.1f}")
    subiu = ys[-1] >= ys[0]
    cor = "#16a34a" if subiu else "#dc2626"
    var = ys[-1] - ys[0]
    return f"""
    <div style="background:#fff;border:1px solid #e5e7eb;border-radius:14px;padding:14px 18px;margin:12px 0">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <h4 style="margin:0">{titulo}</h4>
        <div style="font-weight:700;color:{cor}">{var:+.2f} USDT no período</div>
      </div>
      <svg viewBox="0 0 {w} {h}" style="width:100%;height:auto;margin-top:8px">
        <polyline fill="none" stroke="{cor}" stroke-width="2" points="{' '.join(coords)}"/>
      </svg>
      <div style="display:flex;justify-content:space-between;font-size:12px;color:#9ca3af">
        <span>mín {lo:.2f}</span><span>atual {ys[-1]:.2f}</span><span>máx {hi:.2f}</span>
      </div>
    </div>"""


def _accounting_card(current_value: float) -> str:
    """Contabilidade real: total depositado vs valor atual = lucro/prejuízo de verdade.

    current_value = saldo + P&L aberto (o que você teria se fechasse tudo agora).
    """
    from . import delta as delta_mod
    dep = delta_mod.net_deposits()
    if dep <= 0:
        return ('<div style="background:#fffbeb;border:1px solid #fde68a;border-radius:14px;'
                'padding:12px 16px;margin:10px 0;font-size:13px;color:#92400e">'
                '🧮 <b>Contabilidade real:</b> registre quanto você depositou para ver o '
                'lucro de verdade (sem confundir depósito com ganho). No servidor: '
                '<code>python -m bybit_bot.delta --deposit VALOR --at-start</code></div>')
    pnl = current_value - dep
    pct = pnl / dep * 100 if dep > 0 else 0.0
    cor = "#16a34a" if pnl >= 0 else "#dc2626"
    rotulo = "Lucro de verdade" if pnl >= 0 else "Prejuízo de verdade"
    return f"""
    <div style="background:#fff;border:1px solid #e5e7eb;border-radius:14px;padding:14px 18px;margin:12px 0">
      <h4 style="margin:0 0 10px">🧮 Contabilidade real <span style="font-size:12px;color:#888;font-weight:400">(desde o depósito, já descontando o que você colocou)</span></h4>
      <div style="display:flex;gap:12px;flex-wrap:wrap">
        <div style="flex:1;min-width:140px">
          <div style="font-size:12px;color:#888">Você depositou</div>
          <div style="font-size:20px;font-weight:700">{dep:.2f} USDT</div></div>
        <div style="flex:1;min-width:140px">
          <div style="font-size:12px;color:#888">Vale hoje</div>
          <div style="font-size:20px;font-weight:700">{current_value:.2f} USDT</div></div>
        <div style="flex:1;min-width:140px">
          <div style="font-size:12px;color:#888">{rotulo}</div>
          <div style="font-size:20px;font-weight:700;color:{cor}">{pnl:+.2f} <span style="font-size:14px">({pct:+.1f}%)</span></div></div>
      </div>
    </div>"""


def _delta_section() -> str:
    """Seção do bot Delta (subconta separada): saldo + cesta long/short."""
    from . import delta as delta_mod
    try:
        dc = delta_mod.load_delta_config()
    except Exception:  # noqa: BLE001
        dc = None
    if not dc or not dc.get("api_key") or not dc.get("secret"):
        return ('<div style="background:#eef2ff;border:1px dashed #a5b4fc;border-radius:14px;'
                'padding:16px 20px;margin:14px 0;color:#4f46e5">🔷 <b>Bot Delta</b> ainda não '
                'configurado (.env.delta). Configure as chaves da subconta Delta para vê-lo aqui.</div>')
    try:
        ex = delta_mod.make_delta_client(dc)
        total, free = fetch_balance_usdt(ex)
        positions = fetch_open_positions(ex)
        delta_closed = journal.fetch_closed(ex, limit=100)
    except Exception as exc:  # noqa: BLE001
        return (f'<div style="background:#fff;border:1px solid #e5e7eb;border-radius:14px;'
                f'padding:16px 20px;margin:14px 0;color:#dc2626">🔷 Bot Delta: erro ao ler '
                f'({html.escape(str(exc)[:120])}).</div>')

    longs = [p for p in positions if (p.get("side") or "") == "long"]
    shorts = [p for p in positions if (p.get("side") or "") == "short"]

    def _linhas(lst, verbo):
        if not lst:
            return f'<div style="color:#aaa;font-size:13px">— nenhuma {verbo} —</div>'
        out = ""
        for p in lst:
            cor = "#16a34a" if p["pnl"] >= 0 else "#dc2626"
            sym = html.escape((p["symbol"] or "?").replace("/USDT:USDT", ""))
            out += (f'<div style="display:flex;justify-content:space-between;font-size:14px;padding:2px 0">'
                    f'<span>{sym}</span><span style="color:{cor};font-weight:600">{p["pnl"]:+.3f}</span></div>')
        return out

    pnl_total = sum(p["pnl"] for p in positions)
    cor_total = "#16a34a" if pnl_total >= 0 else "#dc2626"

    # estado do cérebro do Delta (exposição pela queda do saldo)
    cerebro = ""
    if dc.get("brain"):
        try:
            from . import brain as brain_mod
            peak = max(delta_mod._load_peak(), total)
            dd = (peak - total) / peak if peak > 0 else 0.0
            dec = brain_mod.exposure_for_drawdown(dd, dc["brain_warn_dd"], dc["brain_hard_dd"])
            if dec["flatten"]:
                cc, ci = "#dc2626", "⏸ em caixa (disjuntor)"
            elif dec["mult"] < 1.0:
                cc, ci = "#d97706", "🟡 exposição reduzida"
            else:
                cc, ci = "#16a34a", "🟢 exposição normal"
            cerebro = (f'<div style="font-size:13px;margin-top:4px;color:{cc}">🧠 Cérebro: {ci} '
                       f'(topo {peak:.2f} · queda {dd * 100:.1f}%)</div>')
        except Exception:  # noqa: BLE001
            cerebro = ""

    # histórico de fechados do Delta (P&L realizado)
    if delta_closed:
        dh_total = sum(c["pnl"] for c in delta_closed)
        dh_cor = "#16a34a" if dh_total >= 0 else "#dc2626"
        dh_linhas = ""
        for c in reversed(delta_closed[-12:]):
            cor = "#16a34a" if c["pnl"] >= 0 else "#dc2626"
            sym = html.escape((c["symbol"] or "?").replace("/USDT:USDT", ""))
            dh_linhas += (f'<tr style="border-top:1px solid #f0f0f0">'
                          f'<td style="padding:4px">{_fmt_time(c["ts"])}</td>'
                          f'<td style="padding:4px;font-weight:600">{sym}</td>'
                          f'<td style="padding:4px;text-align:right;color:{cor};font-weight:600">{c["pnl"]:+.3f}</td></tr>')
        dhist = (f'<div style="background:#fff;border:1px solid #e5e7eb;border-radius:14px;padding:14px 18px;margin:12px 0">'
                 f'<div style="display:flex;justify-content:space-between;align-items:center">'
                 f'<h4 style="margin:0">📜 Fechados do Delta ({len(delta_closed)})</h4>'
                 f'<div style="font-weight:700;color:{dh_cor}">Realizado {dh_total:+.3f} USDT</div></div>'
                 f'<div style="max-height:260px;overflow-y:auto;margin-top:6px"><table style="width:100%;border-collapse:collapse;font-size:13px">'
                 f'<tr style="color:#999;font-size:12px;text-align:left"><th style="padding:2px 4px">data</th>'
                 f'<th style="padding:2px 4px">par</th><th style="padding:2px 4px;text-align:right">P&amp;L</th></tr>'
                 f'{dh_linhas}</table></div></div>')
    else:
        dhist = ('<div style="color:#9ca3af;font-size:13px;margin:10px 0">📜 Delta ainda sem fechados '
                 '(o 1º rebalance ainda não trocou posições).</div>')

    return f"""
    <hr style="border:0;border-top:2px solid #e5e7eb;margin:28px 0 8px">
    <h2 style="color:#4f46e5;margin:0 0 4px">🔷 Bot Delta <span style="font-size:13px;color:#888">(long/short · 1x)</span></h2>
    <div style="background:#312e81;color:#fff;border-radius:14px;padding:16px 20px;margin:8px 0">
      <div style="font-size:13px;opacity:.8">Saldo da subconta Delta</div>
      <div style="font-size:24px;font-weight:700">{total:.2f} USDT <span style="font-size:13px;opacity:.7">(livre {free:.2f})</span></div>
      <div style="font-size:13px;margin-top:4px;color:{'#4ade80' if pnl_total >= 0 else '#fca5a5'}">P&amp;L aberto: {pnl_total:+.3f} USDT</div>
    </div>
    {cerebro}
    {_accounting_card(total + pnl_total)}
    {_equity_chart()}
    <div style="display:flex;gap:12px;flex-wrap:wrap">
      <div style="flex:1;min-width:220px;background:#fff;border:1px solid #e5e7eb;border-radius:14px;padding:14px 16px">
        <h4 style="margin:0 0 8px;color:#16a34a">🟢 COMPRADAS ({len(longs)})</h4>{_linhas(longs, "compra")}</div>
      <div style="flex:1;min-width:220px;background:#fff;border:1px solid #e5e7eb;border-radius:14px;padding:14px 16px">
        <h4 style="margin:0 0 8px;color:#dc2626">🔴 VENDIDAS ({len(shorts)})</h4>{_linhas(shorts, "venda")}</div>
    </div>
    <div style="font-size:12px;color:#9ca3af;margin-top:8px">Neutro de mercado: ganha quando as compradas sobem mais que as vendidas. Rebalanceia sozinho.</div>
    {dhist}"""


def render_page(refresh: int) -> str:
    cfg = BybitConfig.load()
    cfg.require_keys()
    ex = make_client(cfg)
    total, free = fetch_balance_usdt(ex)
    positions = fetch_open_positions(ex)
    env = "TESTNET" if cfg.use_testnet else "REAL"

    closed = journal.fetch_closed(ex, limit=100)
    opens = journal.load_opens()
    stats_html = _stats_card(ex, cfg, closed=closed, opens=opens)
    brain_html = _brain_card(cfg, closed)
    history_html = _history_card(ex, closed=closed, opens=opens)
    delta_html = _delta_section()
    launch_html = _launch_section()
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
  <h1 style="color:#0b3d91;margin:0 0 4px">🤖 Bot Sniper <span style="font-size:13px;color:#888">(só compra · 5x)</span></h1>
  <div style="color:#6b7280;font-size:13px;margin-bottom:14px">Conta {env} · atualiza a cada {refresh}s</div>
  <div style="background:#111827;color:#fff;border-radius:14px;padding:16px 20px;margin-bottom:8px">
    <div style="font-size:13px;opacity:.8">Saldo da subconta</div>
    <div style="font-size:26px;font-weight:700">{total:.2f} USDT <span style="font-size:14px;opacity:.7">(livre {free:.2f})</span></div>
  </div>
  {brain_html}
  {stats_html}
  {corpo}
  {history_html}
  {delta_html}
  {launch_html}
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
