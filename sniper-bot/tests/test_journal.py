"""Testes do diário CSV."""

import csv

from sniper.journal import FIELDS, Journal


def _read(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_cria_cabecalho(tmp_path):
    p = tmp_path / "t.csv"
    Journal(str(p))
    with open(p, newline="", encoding="utf-8") as f:
        assert next(csv.reader(f)) == FIELDS


def test_open_skip_close(tmp_path):
    p = str(tmp_path / "t.csv")
    j = Journal(p)
    trade = {"symbol": "AUSDT", "side": "BUY", "qty": 30,
             "entry": 2.0, "tp": 2.2, "sl": 1.9}
    j.record_open(trade, "paper")
    j.record_skip("BUSDT", "paper", "livro raso")
    j.record_close(trade, "paper", 2.2, 6.0, 0.30, "WIN")

    rows = _read(p)
    assert [r["status"] for r in rows] == ["OPEN", "SKIPPED", "WIN"]
    assert rows[2]["pnl_usdt"] == "6.0"
    assert rows[1]["note"] == "livro raso"


def test_anexa_sem_reescrever_cabecalho(tmp_path):
    p = str(tmp_path / "t.csv")
    Journal(p)
    Journal(p)  # segunda criação não deve duplicar cabeçalho
    j = Journal(p)
    j.record_skip("X", "paper", "teste")
    rows = _read(p)
    assert len(rows) == 1
