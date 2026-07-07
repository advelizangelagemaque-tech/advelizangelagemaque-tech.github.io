"""Testes da escolha do provedor de flash loan (pega o mais barato)."""

from flashsim.chains import best_flash_provider


def test_polygon_pega_balancer_de_graca():
    name, fee = best_flash_provider("polygon")
    assert name == "Balancer" and fee == 0        # 0% é melhor que a Aave (0.05%)


def test_bsc_cai_na_aave():
    name, fee = best_flash_provider("bsc")
    assert fee == 5                                # sem Balancer na BSC


def test_rede_desconhecida_tem_default():
    name, fee = best_flash_provider("rede_que_nao_existe")
    assert fee == 5                                # cai no default seguro (Aave)
