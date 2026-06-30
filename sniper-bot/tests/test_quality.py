"""Testes do filtro de qualidade (spread, profundidade, volume)."""

from sniper.quality import check_quality
from tests.conftest import FakeClient, make_cfg


def test_aprova_livro_bom(sym):
    cfg = make_cfg(max_spread_pct=0.03, min_book_depth_usdt=1000)
    client = FakeClient(bids=[["1.99", "1000"]], asks=[["2.00", "1000"]])
    ok, reason, m = check_quality(client, sym, cfg)
    assert ok and reason == "aprovado"
    assert m["spread_pct"] < 0.01
    assert m["book_depth_usdt"] > 3000


def test_reprova_spread_largo(sym):
    cfg = make_cfg(max_spread_pct=0.03)
    client = FakeClient(bids=[["1.50", "1000"]], asks=[["2.00", "1000"]])
    ok, reason, _ = check_quality(client, sym, cfg)
    assert not ok and "spread" in reason


def test_reprova_livro_raso(sym):
    cfg = make_cfg(min_book_depth_usdt=1000)
    client = FakeClient(bids=[["1.99", "10"]], asks=[["2.00", "10"]])
    ok, reason, _ = check_quality(client, sym, cfg)
    assert not ok and "profundidade" in reason


def test_reprova_livro_vazio(sym):
    cfg = make_cfg()
    client = FakeClient(bids=[], asks=[])
    ok, reason, _ = check_quality(client, sym, cfg)
    assert not ok and "vazio" in reason


def test_reprova_volume_baixo(sym):
    cfg = make_cfg(min_quote_volume=1_000_000)
    client = FakeClient(bids=[["1.99", "1000"]], asks=[["2.00", "1000"]], quote_volume=100)
    ok, reason, _ = check_quality(client, sym, cfg)
    assert not ok and "volume" in reason


def test_limites_desligados_aprovam(sym):
    # tudo 0 = sem filtro, aprova mesmo com livro raso
    cfg = make_cfg(max_spread_pct=0, min_book_depth_usdt=0, min_quote_volume=0)
    client = FakeClient(bids=[["1.0", "1"]], asks=[["1.5", "1"]])
    ok, _, _ = check_quality(client, sym, cfg)
    assert ok
