"""Testes do medidor de entrada."""

from bybit_bot.entry_check import entry_score, range_position, rsi, sma


def test_sma():
    assert sma([1, 2, 3, 4], 2) == 3.5
    assert sma([1, 2], 5) is None


def test_rsi_extremos():
    subindo = list(range(1, 40))                 # sempre sobe -> RSI satura em 100
    assert rsi(subindo, 14) == 100.0
    caindo = list(range(40, 1, -1))              # sempre cai -> RSI perto de 0
    assert rsi(caindo, 14) < 5


def test_range_position():
    closes = [10, 20, 30, 15]                    # min 10, max 30, atual 15
    assert abs(range_position(closes, 90) - 0.25) < 1e-9   # (15-10)/(30-10)
    assert range_position([5, 5, 5], 90) == 0.5           # faixa achatada


def test_entry_score_sobrecomprado_manda_esperar():
    # série que só sobe -> RSI>=70 -> veredito ESPERE, nota baixa (perto do topo)
    closes = [100 * (1.02 ** i) for i in range(120)]
    e = entry_score(closes)
    assert e["rsi"] >= 70
    assert "ESPERE" in e["verdict"]
    assert e["score"] < 40


def test_entry_score_desconto_e_boa_zona():
    # sobe muito e depois cai forte -> RSI baixo e preço perto da mínima -> BOA ZONA
    closes = [100 * (1.02 ** i) for i in range(90)]
    closes += [closes[-1] * (0.97 ** i) for i in range(1, 30)]
    e = entry_score(closes)
    assert e["rsi"] <= 40
    assert e["score"] >= 60
    assert "BOA ZONA" in e["verdict"] or "NEUTRO" in e["verdict"]


def test_entry_score_sem_dados():
    e = entry_score([1, 2, 3])
    assert e["score"] is None
