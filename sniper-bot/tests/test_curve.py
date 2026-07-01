"""Testes do leitor da curva de liquidez e do filtro de tração/momentum."""

from struct import pack

from solana_sniper.curve import curve_gate, decode_curve


def _raw(vtr, vsr, rtr, rsr, tts, complete=False):
    return b"\x00" * 8 + pack("<QQQQQ", vtr, vsr, rtr, rsr, tts) + (b"\x01" if complete else b"\x00")


def test_decode_curve():
    c = decode_curve(_raw(1_000_000_000_000, 30_000_000_000, 800_000_000_000,
                          5_000_000_000, 1_000_000_000_000))
    assert c["sol_in_curve"] == 5.0          # 5e9 lamports
    assert c["mcap_sol"] == 30.0             # vsr*tts/vtr /1e9
    assert c["complete"] is False


def test_decode_curve_curto_demais():
    assert decode_curve(b"\x00" * 10) is None


def _c(sol):
    return {"sol_in_curve": sol, "mcap_sol": sol * 6, "complete": False}


def test_gate_tracao_minima():
    ok, r = curve_gate(_c(5), None, 1.0, 0.0, False)
    assert ok
    ok, r = curve_gate(_c(0.5), None, 1.0, 0.0, False)
    assert not ok and "tração" in r


def test_gate_tarde_demais():
    ok, r = curve_gate(_c(40), None, 0.0, 30.0, False)
    assert not ok and "tarde" in r


def test_gate_momentum():
    ok, _ = curve_gate(_c(5), _c(7), 1.0, 0.0, True)
    assert ok
    ok, r = curve_gate(_c(5), _c(5), 1.0, 0.0, True)
    assert not ok and "momentum" in r


def test_gate_graduou():
    c = {"sol_in_curve": 80, "mcap_sol": 400, "complete": True}
    ok, r = curve_gate(c, None, 0.0, 0.0, False)
    assert not ok and "graduou" in r


def test_gate_sem_curva():
    ok, r = curve_gate(None, None, 0.0, 0.0, False)
    assert not ok and "não encontrada" in r
