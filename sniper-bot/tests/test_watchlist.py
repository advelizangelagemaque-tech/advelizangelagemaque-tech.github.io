"""Testes da watchlist (parte pura)."""

from bybit_bot.watchlist import (load_watchlist, new_signals, normalize_symbol,
                                 refresh_symbols, watchlist_text)


def test_refresh_symbols_mantem_ativos_corta_frios():
    results = [
        {"symbol": "A/USDT:USDT", "light": "short"},   # candidato -> mantém
        {"symbol": "B/USDT:USDT", "light": "wait"},    # candidato -> mantém
        {"symbol": "C/USDT:USDT", "light": "none"},    # frio -> corta
    ]
    gainers = ["D/USDT:USDT", "A/USDT:USDT"]            # novo em alta + um repetido
    out = refresh_symbols(results, gainers)
    assert out == ["A/USDT:USDT", "B/USDT:USDT", "D/USDT:USDT"]   # sem C, sem repetir A


def test_watchlist_text_serializa_tickers():
    txt = watchlist_text(["SQD/USDT:USDT", "BSP/USDT:USDT"])
    assert "SQD" in txt and "BSP" in txt
    assert load_watchlist(txt) == ["SQD/USDT:USDT", "BSP/USDT:USDT"]   # ida-e-volta


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


def test_new_signals_cooldown_nao_repete_o_mesmo():
    # Caso real KORU/VELVET: piscou 🟢/🔴 e re-disparou o mesmo alerta.
    last: dict = {}
    cd = 100.0
    fired = new_signals(set(), {"KORU"}, last, now=1000.0, cooldown=cd)
    assert fired == ["KORU"]                         # primeira virada -> avisa
    last["KORU"] = 1000.0                            # o run() marca o horário
    # piscou e voltou 30s depois -> DENTRO do cooldown -> NÃO repete
    assert new_signals(set(), {"KORU"}, last, now=1030.0, cooldown=cd) == []
    # voltou bem depois (passou do cooldown) -> pode avisar de novo
    assert new_signals(set(), {"KORU"}, last, now=1200.0, cooldown=cd) == ["KORU"]


def test_new_signals_sem_cooldown_mantem_comportamento_antigo():
    # cooldown desligado (0) -> igual antes, dispara toda transição
    last: dict = {"B/USDT:USDT": 500.0}
    assert new_signals(set(), {"B/USDT:USDT"}, last, now=510.0, cooldown=0.0) == ["B/USDT:USDT"]
