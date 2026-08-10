"""Testes da watchlist (parte pura)."""

from bybit_bot.watchlist import load_watchlist, new_signals, normalize_symbol


def test_normalize_symbol():
    assert normalize_symbol("pepe") == "PEPE/USDT:USDT"
    assert normalize_symbol("SQD/USDT:USDT") == "SQD/USDT:USDT"
    assert normalize_symbol("  gwei ") == "GWEI/USDT:USDT"
    assert normalize_symbol("") is None
    assert normalize_symbol("# comentário") is None


def test_load_watchlist_sem_repetir():
    txt = "SQD\nBSP\n# nota\nsqd\n\nGWEI\n"
    assert load_watchlist(txt) == ["SQD/USDT:USDT", "BSP/USDT:USDT", "GWEI/USDT:USDT"]


def test_new_signals_detecta_transicao():
    prev = {"A/USDT:USDT"}
    agora = {"A/USDT:USDT", "B/USDT:USDT"}         # B acabou de virar
    assert new_signals(prev, agora) == ["B/USDT:USDT"]
    assert new_signals(agora, agora) == []          # nada novo
    assert new_signals(agora, {"A/USDT:USDT"}) == []  # saiu não é alerta
