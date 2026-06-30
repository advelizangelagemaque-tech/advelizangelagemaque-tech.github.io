"""Testes de validação de configuração."""

import pytest

from tests.conftest import make_cfg


def test_config_valida_ok():
    cfg = make_cfg()
    assert cfg.leverage == 3


def test_stop_loss_obrigatorio():
    with pytest.raises(ValueError):
        make_cfg(stop_loss_pct=0)


def test_leverage_fora_do_limite():
    with pytest.raises(ValueError):
        make_cfg(leverage=200)


def test_sem_chaves_ok_para_paper():
    # paper/dry não exigem chaves (só leem dados públicos)
    cfg = make_cfg(api_key="", api_secret="")
    assert cfg.exchange == "binance"


def test_sem_chaves_falha_no_live():
    cfg = make_cfg(api_key="", api_secret="")
    with pytest.raises(ValueError):
        cfg.require_keys_for_live()


def test_trailing_callback_fora_do_limite():
    with pytest.raises(ValueError):
        make_cfg(use_trailing=True, trailing_callback_pct=0.10)  # 10% > limite 5%


def test_trailing_callback_ignorado_se_desligado():
    # callback inválido não importa se trailing está desligado
    cfg = make_cfg(use_trailing=False, trailing_callback_pct=0.10)
    assert cfg.use_trailing is False


def test_cooldown_negativo_falha():
    with pytest.raises(ValueError):
        make_cfg(cooldown_seconds=-1)


def test_poll_interval_minimo():
    with pytest.raises(ValueError):
        make_cfg(poll_interval_ms=10)
