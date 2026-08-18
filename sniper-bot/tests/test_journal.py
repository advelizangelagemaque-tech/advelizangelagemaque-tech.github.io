"""Testes do diário de operações (parte pura)."""

from bybit_bot.journal import pnl_pct, summarize


def test_pnl_pct_long_e_short():
    assert abs(pnl_pct("long", 100, 110) - 0.10) < 1e-9     # long sobe -> ganha
    assert abs(pnl_pct("short", 100, 90) - 0.10) < 1e-9     # short cai -> ganha
    assert abs(pnl_pct("short", 100, 110) + 0.10) < 1e-9    # short sobe -> perde
    assert pnl_pct("long", 0, 10) == 0.0                    # entrada inválida
    assert pnl_pct("neutro", 100, 130) == 0.0              # neutro não é direcional


def test_summarize_conta_acertos_e_total():
    trades = [{"result": "3.0"}, {"result": "-1.0"}, {"result": "2.0"}, {"result": ""}]
    s = summarize(trades)
    assert s["n"] == 3                      # ignora o vazio
    assert s["wins"] == 2 and s["losses"] == 1
    assert abs(s["win_rate"] - 2 / 3) < 1e-9
    assert abs(s["total"] - 4.0) < 1e-9
    assert abs(s["expectancy"] - 4.0 / 3) < 1e-9


def test_summarize_vazio():
    s = summarize([])
    assert s["n"] == 0 and s["total"] == 0.0 and s["win_rate"] == 0.0
