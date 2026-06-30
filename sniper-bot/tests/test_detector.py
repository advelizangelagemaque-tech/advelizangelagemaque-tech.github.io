"""Testes de detecção de listagens (parsing e diffing)."""

import pytest

from sniper.detector import ListingDetector, parse_symbols
from tests.conftest import exchange_info


def test_parse_filtra_status_e_contrato():
    info = exchange_info(["BTCUSDT"])
    assert "BTCUSDT" in parse_symbols(info, "USDT")
    # status não-TRADING é ignorado
    assert parse_symbols(exchange_info(["X"], status="BREAK"), "USDT") == {}
    # contrato não-perpétuo é ignorado
    assert parse_symbols(exchange_info(["X"], contract="CURRENT_QUARTER"), "USDT") == {}
    # outra moeda de cotação é ignorada
    assert parse_symbols(exchange_info(["XBUSD"], quote="BUSD"), "USDT") == {}


def test_parse_extrai_filtros():
    s = parse_symbols(exchange_info(["BTCUSDT"]), "USDT")["BTCUSDT"]
    assert s.step_size == 0.001
    assert s.tick_size == 0.01
    assert s.min_notional == 5.0


def test_detect_new_reporta_apenas_novos():
    d = ListingDetector("USDT")
    d.prime(exchange_info(["BTCUSDT", "ETHUSDT"]))
    novos = d.detect_new(exchange_info(["BTCUSDT", "ETHUSDT", "NEWUSDT"]))
    assert [x.symbol for x in novos] == ["NEWUSDT"]


def test_detect_new_nao_redispara():
    d = ListingDetector("USDT")
    d.prime(exchange_info(["BTCUSDT"]))
    d.detect_new(exchange_info(["BTCUSDT", "NEWUSDT"]))
    # segunda chamada com o mesmo conjunto não deve trazer nada
    assert d.detect_new(exchange_info(["BTCUSDT", "NEWUSDT"])) == []


def test_detect_new_sem_prime_falha():
    with pytest.raises(RuntimeError):
        ListingDetector("USDT").detect_new(exchange_info(["BTCUSDT"]))
