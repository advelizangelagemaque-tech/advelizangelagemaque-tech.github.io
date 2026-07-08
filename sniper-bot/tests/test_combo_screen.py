"""Testes do rastreador de carteira do Futures Combo (funding)."""

from bybit_bot.combo_screen import annualized, build_combo, funding_rows


def _tick(funding, vol=100e6, pct=5.0):
    return {"info": {"fundingRate": str(funding)}, "quoteVolume": vol, "percentage": pct}


def test_funding_rows_filtra_liquidez_e_par():
    tickers = {
        "BTC/USDT:USDT": _tick(0.0001, vol=500e6),
        "FINA/USDT:USDT": _tick(0.001, vol=1e6),        # ilíquida -> fora
        "ETH/USDT": _tick(0.0002, vol=500e6),           # não é perp (:USDT) -> fora
    }
    rows = funding_rows(tickers, min_vol_usdt=30e6)
    assert [r["symbol"] for r in rows] == ["BTC/USDT:USDT"]
    assert rows[0]["funding"] == 0.0001


def test_annualized():
    # 0.01%/8h * 3 * 365 = 10.95%/ano
    assert abs(annualized(0.0001) - 0.1095) < 1e-6


def test_build_combo_short_alto_long_baixo():
    tickers = {
        "A/USDT:USDT": _tick(0.0010),     # funding alto -> SHORT
        "B/USDT:USDT": _tick(0.0008),
        "C/USDT:USDT": _tick(0.0000),
        "D/USDT:USDT": _tick(-0.0005),    # funding negativo -> LONG
    }
    rows = funding_rows(tickers, min_vol_usdt=30e6)
    combo = build_combo(rows, k=1)
    assert combo["shorts"][0]["symbol"] == "A/USDT:USDT"   # paga mais funding
    assert combo["longs"][0]["symbol"] == "D/USDT:USDT"    # funding mais negativo
    assert combo["carry_anual_pct"] > 0                    # recebe dos dois lados


def test_build_combo_descarta_volatil():
    tickers = {
        "A/USDT:USDT": _tick(0.0010, pct=80.0),   # +80% no dia -> volátil demais, fora
        "B/USDT:USDT": _tick(0.0009, pct=5.0),
        "C/USDT:USDT": _tick(-0.0004, pct=3.0),
    }
    rows = funding_rows(tickers, min_vol_usdt=30e6)
    combo = build_combo(rows, k=1, max_vol24h=25.0)
    syms = [r["symbol"] for r in combo["shorts"] + combo["longs"]]
    assert "A/USDT:USDT" not in syms          # cortada por volatilidade
    assert "B/USDT:USDT" in syms and "C/USDT:USDT" in syms


def test_build_combo_pesos_somam_neutro():
    tickers = {f"{c}/USDT:USDT": _tick(f) for c, f in
               [("A", 0.001), ("B", 0.0008), ("C", 0.0), ("D", -0.0003),
                ("E", -0.0006), ("F", -0.001)]}
    rows = funding_rows(tickers, min_vol_usdt=30e6)
    combo = build_combo(rows, k=3)
    n = len(combo["longs"]) + len(combo["shorts"])
    assert abs(combo["weight_pct"] * n - 100.0) < 1.0   # pesos ~100% no total
