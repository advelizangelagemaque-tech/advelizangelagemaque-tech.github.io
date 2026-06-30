"""Testes do resumo de desempenho."""

import csv

import pytest

from sniper.journal import FIELDS
from sniper.summary import summarize


def _write(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})


def test_summarize_estatisticas(tmp_path):
    p = str(tmp_path / "t.csv")
    _write(p, [
        {"status": "WIN", "pnl_usdt": "6"},
        {"status": "WIN", "pnl_usdt": "6"},
        {"status": "LOSS", "pnl_usdt": "-3"},
        {"status": "SKIPPED"},
        {"status": "OPEN"},
    ])
    s = summarize(p)
    assert s["wins"] == 2 and s["losses"] == 1
    assert s["skipped"] == 1 and s["open"] == 1
    assert s["closed"] == 3
    assert s["win_rate"] == pytest.approx(2 / 3)
    assert s["total_pnl"] == pytest.approx(9.0)
    assert s["expectancy"] == pytest.approx(3.0)
    assert s["profit_factor"] == pytest.approx(4.0)  # 12 / 3


def test_summarize_sem_fechados_nao_divide_por_zero(tmp_path):
    p = str(tmp_path / "t.csv")
    _write(p, [{"status": "OPEN"}, {"status": "SKIPPED"}])
    s = summarize(p)
    assert s["closed"] == 0
    assert s["win_rate"] == 0.0
    assert s["expectancy"] == 0.0
    assert s["profit_factor"] == float("inf")
