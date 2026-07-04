"""Testes da lógica do sniper de lançamentos (detecção + análise)."""

from bybit_bot.launch import (
    detect_new,
    nearest_ret,
    perp_symbols,
    ret_pct,
    summarize,
)


def test_perp_symbols():
    tickers = {"AAA/USDT:USDT": {}, "BBB/USDT": {}, "CCC/USDT:USDT": {}}
    assert perp_symbols(tickers) == {"AAA/USDT:USDT", "CCC/USDT:USDT"}


def test_detect_new():
    known = {"A", "B"}
    current = {"A", "B", "C", "D"}
    assert detect_new(current, known) == ["C", "D"]
    assert detect_new(known, known) == []


def test_ret_pct():
    assert ret_pct(100, 110) == 0.10
    assert ret_pct(100, 80) == -0.20
    assert ret_pct(0, 50) == 0.0


def test_nearest_ret():
    rows = [
        {"elapsed_min": "0.5", "ret_pct": "0.02"},
        {"elapsed_min": "5.2", "ret_pct": "0.15"},
        {"elapsed_min": "31.0", "ret_pct": "-0.10"},
    ]
    assert nearest_ret(rows, 5) == 0.15         # mais perto de 5 min
    assert nearest_ret(rows, 30) == -0.10       # mais perto de 30 min
    assert nearest_ret(rows, 60) is None        # nada perto de 60 (fora da tolerância)


def test_summarize():
    rows = [
        # dois lançamentos, ambos com dado em ~5 min
        {"symbol": "X", "elapsed_min": "5.0", "ret_pct": "0.20"},
        {"symbol": "Y", "elapsed_min": "5.0", "ret_pct": "-0.40"},
    ]
    resumo, n = summarize(rows, checkpoints=[5])
    assert n == 2
    assert resumo[5]["n"] == 2
    assert abs(resumo[5]["media"] - (-0.10)) < 1e-9   # (0.20 - 0.40)/2
    assert resumo[5]["pct_up"] == 0.5                  # 1 de 2 subiu
