"""Testes da lógica de saída (TP/SL fixo e trailing stop)."""

import pytest

from sniper.position import update_and_check_exit
from tests.conftest import make_cfg


# ---- TP/SL fixo ----

def test_fixo_long_tp():
    cfg = make_cfg(use_trailing=False)
    t = {"side": "BUY", "entry": 2.0, "tp": 2.2, "sl": 1.9}
    assert update_and_check_exit(t, 2.25, cfg) == (2.2, "WIN")


def test_fixo_long_sl():
    cfg = make_cfg(use_trailing=False)
    t = {"side": "BUY", "entry": 2.0, "tp": 2.2, "sl": 1.9}
    assert update_and_check_exit(t, 1.80, cfg) == (1.9, "LOSS")


def test_fixo_aberto():
    cfg = make_cfg(use_trailing=False)
    t = {"side": "BUY", "entry": 2.0, "tp": 2.2, "sl": 1.9}
    assert update_and_check_exit(t, 2.05, cfg) == (None, None)


def test_fixo_short_tp():
    cfg = make_cfg(use_trailing=False)
    t = {"side": "SELL", "entry": 2.0, "tp": 1.8, "sl": 2.1}
    assert update_and_check_exit(t, 1.75, cfg) == (1.8, "WIN")


# ---- Trailing ----

def test_trailing_long_segue_pico_e_fecha_win():
    cfg = make_cfg(use_trailing=True, trailing_callback_pct=0.05)
    t = {"side": "BUY", "entry": 2.0, "tp": 2.2, "sl": 1.9}
    assert update_and_check_exit(t, 2.1, cfg) == (None, None)   # antes de ativar
    assert update_and_check_exit(t, 2.2, cfg) == (None, None)   # ativa, peak=2.2
    assert t["trail_active"] and t["peak"] == 2.2
    assert update_and_check_exit(t, 3.0, cfg) == (None, None)   # peak sobe p/ 3.0
    assert t["peak"] == 3.0
    exit_p, st = update_and_check_exit(t, 2.84, cfg)            # recua < 2.85
    assert st == "WIN" and exit_p == pytest.approx(2.84)


def test_trailing_stop_duro_antes_de_ativar():
    cfg = make_cfg(use_trailing=True, trailing_callback_pct=0.05)
    t = {"side": "BUY", "entry": 2.0, "tp": 2.2, "sl": 1.9}
    assert update_and_check_exit(t, 1.85, cfg) == (1.9, "LOSS")


def test_trailing_short():
    cfg = make_cfg(use_trailing=True, trailing_callback_pct=0.05)
    t = {"side": "SELL", "entry": 2.0, "tp": 1.8, "sl": 2.1}
    assert update_and_check_exit(t, 1.8, cfg) == (None, None)   # ativa, peak=1.8
    assert update_and_check_exit(t, 1.5, cfg) == (None, None)   # peak desce p/ 1.5
    exit_p, st = update_and_check_exit(t, 1.58, cfg)            # sobe > 1.575
    assert st == "WIN" and exit_p == pytest.approx(1.58)
