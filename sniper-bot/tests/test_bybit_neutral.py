"""Testes da trava de neutralidade do Delta (long/short sempre equilibrados)."""

import os
import tempfile

from bybit_bot.delta import _add_skip, _load_skip, eligible_rows, excess_to_close


def _p(sym, side, pnl):
    return {"symbol": sym, "side": side, "pnl": pnl}


def test_equilibrado_nao_fecha_nada():
    pos = [_p("A", "long", 1), _p("B", "long", -1),
           _p("C", "short", 2), _p("D", "short", -2)]
    assert excess_to_close(pos) == []


def test_excesso_de_long_fecha_os_piores_longs():
    # 5 long x 3 short (exatamente o caso do painel) -> fecha 2 longs, os piores
    pos = [_p("TAC", "long", 0.26), _p("EVAA", "long", 1.17), _p("BLUR", "long", -1.24),
           _p("M", "long", -0.93), _p("EDGE", "long", -2.16),
           _p("VANRY", "short", -0.50), _p("LAB", "short", 1.23), _p("MAGMA", "short", 0.66)]
    fechar = excess_to_close(pos)
    assert set(fechar) == {"EDGE", "BLUR"}      # os 2 longs com pior P&L


def test_excesso_de_short_fecha_os_piores_shorts():
    pos = [_p("A", "long", 0.5),
           _p("X", "short", -3.0), _p("Y", "short", -1.0), _p("Z", "short", 2.0)]
    assert excess_to_close(pos) == ["X", "Y"]   # 3 short x 1 long -> fecha 2 piores shorts


def test_so_um_lado_fecha_ate_zerar_o_outro():
    pos = [_p("A", "long", 1), _p("B", "long", 2)]   # 2 long, 0 short
    assert set(excess_to_close(pos)) == {"A", "B"}   # sem hedge -> fecha os dois


def test_skip_list_persiste_e_nao_duplica():
    p = os.path.join(tempfile.mkdtemp(), "skip.txt")
    assert _load_skip(p) == set()
    _add_skip("KORU/USDT:USDT", p)
    _add_skip("SOXL/USDT:USDT", p)
    _add_skip("KORU/USDT:USDT", p)                    # repetido não duplica
    skip = _load_skip(p)
    assert skip == {"KORU/USDT:USDT", "SOXL/USDT:USDT"}


def test_cesta_ignora_tokens_da_skip_list():
    tickers = {
        "AAA/USDT:USDT": {"percentage": 10, "quoteVolume": 9e6},
        "KORU/USDT:USDT": {"percentage": 8, "quoteVolume": 9e6},   # será pulado
        "BBB/USDT:USDT": {"percentage": 5, "quoteVolume": 9e6},
    }
    rows = eligible_rows(tickers, 5e6)
    skip = {"KORU/USDT:USDT"}
    filtrado = [r for r in rows if r["symbol"] not in skip]
    syms = {r["symbol"] for r in filtrado}
    assert "KORU/USDT:USDT" not in syms and "AAA/USDT:USDT" in syms
