"""Testes do pegador de moedas em alta."""

from bybit_bot.top_gainers import merge_into_watchlist, top_gainers


def _t(pct, vol=100e6):
    return {"percentage": pct, "quoteVolume": vol}


def test_top_gainers_ordena_e_filtra():
    tickers = {
        "AAA/USDT:USDT": _t(50),
        "BBB/USDT:USDT": _t(80),
        "CCC/USDT:USDT": _t(10),
        "FINA/USDT:USDT": _t(200, vol=1e6),     # ilíquida -> fora
        "ETH/USDT": _t(90),                     # não é perp -> fora
    }
    top = top_gainers(tickers, n=2, min_vol_usdt=30e6)
    assert [r["symbol"] for r in top] == ["BBB/USDT:USDT", "AAA/USDT:USDT"]


def test_merge_sem_repetir():
    existing = "SQD\nGWEI\n"
    out = merge_into_watchlist(existing, ["GWEI/USDT:USDT", "PEPE/USDT:USDT"])
    assert out == "SQD\nGWEI\nPEPE\n"          # GWEI já existe, só PEPE entra


def test_merge_nada_novo_nao_muda():
    existing = "SQD\nGWEI\n"
    assert merge_into_watchlist(existing, ["SQD/USDT:USDT"]) == existing


def test_merge_arquivo_vazio():
    assert merge_into_watchlist("", ["AAA/USDT:USDT"]) == "AAA\n"
