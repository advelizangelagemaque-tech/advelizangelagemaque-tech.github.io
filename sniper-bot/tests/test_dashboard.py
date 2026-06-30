"""Testes do gerador de dashboard HTML."""

import csv

from sniper.dashboard import build_html, _pnl_curve_svg, _closed_pnls
from sniper.journal import FIELDS


def _write(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})


def test_curva_vazia_mostra_aviso():
    svg = _pnl_curve_svg([])
    assert "Sem operações" in svg


def test_curva_gera_svg():
    svg = _pnl_curve_svg([6.0, -3.0, 6.0])
    assert "<polyline" in svg and "PnL acumulado" in svg


def test_closed_pnls_ignora_open_e_skip(tmp_path):
    p = str(tmp_path / "t.csv")
    _write(p, [
        {"status": "OPEN"},
        {"status": "SKIPPED"},
        {"status": "WIN", "symbol": "AUSDT", "pnl_usdt": "6"},
        {"status": "LOSS", "symbol": "BUSDT", "pnl_usdt": "-3"},
    ])
    assert _closed_pnls(p) == [("AUSDT", 6.0), ("BUSDT", -3.0)]


def test_build_html_contem_estatisticas(tmp_path):
    p = str(tmp_path / "t.csv")
    _write(p, [
        {"status": "WIN", "symbol": "AUSDT", "pnl_usdt": "6"},
        {"status": "WIN", "symbol": "BUSDT", "pnl_usdt": "6"},
        {"status": "LOSS", "symbol": "CUSDT", "pnl_usdt": "-3"},
    ])
    page = build_html(p)
    assert "<!doctype html>" in page
    assert "Dashboard" in page
    assert "66.7%" in page          # win rate 2/3
    assert "+9.00" in page          # PnL total
    assert "AUSDT" in page          # aparece na tabela
