"""Testes do diário e das estatísticas (aprendizado) do agente Bybit."""

from types import SimpleNamespace

from bybit_bot.journal import (
    classify_exit,
    compute_stats,
    record_open,
    stats_by_dip_band,
    suggest_dip_min,
)


def test_classify_exit_segue_o_resultado():
    # rótulo deve seguir o P&L, nunca 'TP' com prejuízo
    assert classify_exit({"pnl": 2.5}) == "TP"
    assert classify_exit({"pnl": -1.2}) == "SL"
    assert classify_exit({"pnl": 0.0}) == "SL"


def test_compute_stats_vazio():
    st = compute_stats([])
    assert st["count"] == 0 and st["total_pnl"] == 0.0


def test_compute_stats():
    closed = [{"pnl": 2.0}, {"pnl": -1.0}, {"pnl": 3.0}, {"pnl": -1.0}]
    st = compute_stats(closed)
    assert st["count"] == 4
    assert st["wins"] == 2 and st["losses"] == 2
    assert st["win_rate"] == 0.5
    assert st["total_pnl"] == 3.0
    assert st["avg_win"] == 2.5          # (2+3)/2
    assert st["avg_loss"] == -1.0
    assert st["expectancy"] == 0.75      # 3/4
    assert st["profit_factor"] == 2.5    # 5 / 2


def test_stats_by_dip_band():
    opens = [
        {"symbol": "A/USDT:USDT", "ts": "100", "dip": "0.04"},
        {"symbol": "B/USDT:USDT", "ts": "100", "dip": "0.08"},
    ]
    closed = [
        {"symbol": "A/USDT:USDT", "ts": 200, "pnl": 1.5},
        {"symbol": "B/USDT:USDT", "ts": 200, "pnl": -0.5},
    ]
    bands = stats_by_dip_band(closed, opens)
    assert bands["3-6%"]["count"] == 1 and bands["3-6%"]["pnl"] == 1.5      # dip 0.04
    assert bands["6-10%"]["count"] == 1 and bands["6-10%"]["pnl"] == -0.5   # dip 0.08


def test_suggest_dip_min_sem_amostra():
    cfg = SimpleNamespace(autotune_min_trades=20, dip_min=0.03)
    assert suggest_dip_min([{"pnl": 1}], [], cfg) is None


def test_record_open_e_load(tmp_path):
    from bybit_bot import journal
    p = tmp_path / "opens.csv"
    row = {"ts": 1, "symbol": "X/USDT:USDT", "entry": 1.0, "tp": 1.06, "sl": 0.97,
           "pct_24h": 0.3, "dip": 0.05, "qty": 10}
    record_open(row, path=str(p))
    rows = journal.load_opens(str(p))
    assert len(rows) == 1 and rows[0]["symbol"] == "X/USDT:USDT"
