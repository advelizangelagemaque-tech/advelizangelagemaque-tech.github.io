"""Testes do medidor de entrada."""

from bybit_bot.entry_check import (entry_score, range_position, rsi, sma,
                                   stoch_rsi)


def test_stoch_rsi_extremos():
    base = [100 + (i % 2) for i in range(20)]                    # base com micro-oscilação
    subindo = base + [100 * (1.05 ** i) for i in range(18)]      # RSI no topo da faixa
    assert stoch_rsi(subindo) >= 99
    caindo = (base + [100 * (1.05 ** i) for i in range(12)]
              + [100 * (1.05 ** 11) * (0.97 ** i) for i in range(1, 9)])  # RSI no fundo
    assert stoch_rsi(caindo) <= 1
    assert stoch_rsi([1, 2, 3]) is None                         # dados insuficientes


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
