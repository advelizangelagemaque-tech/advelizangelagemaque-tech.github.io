"""Testes do motor de arbitragem triangular (a caça à fresta no loop)."""

from flashsim.triangular import (Leg, cycle_edge, evaluate_cycle,
                                 optimize_cycle, simulate_cycle)


def _leg(tin, tout, rin, rout, fee=30):
    return Leg("DEX", tin, tout, rin, rout, fee)


def test_ciclo_neutro_nao_lucra():
    # três pools 1:1, só as taxas -> volta menos do que entrou
    legs = [_leg("USDC", "A", 1e6, 1e6), _leg("A", "B", 1e6, 1e6),
            _leg("B", "USDC", 1e6, 1e6)]
    assert simulate_cycle(1000, legs) < 1000          # taxas comem
    x, gross = optimize_cycle(legs)
    assert x == 0.0 and gross == 0.0                  # melhor não entrar


def test_fresta_no_loop_da_lucro():
    # cada par parece ~1:1, mas a última perna paga 3% a mais -> o loop rende
    legs = [_leg("USDC", "A", 1e6, 1e6), _leg("A", "B", 1e6, 1e6),
            _leg("B", "USDC", 1e6, 1.03e6)]
    x, gross = optimize_cycle(legs)
    assert x > 0 and gross > 0                         # achou a fresta

def test_evaluate_cycle_desconta_gas():
    legs = [_leg("USDC", "A", 1e6, 1e6), _leg("A", "B", 1e6, 1e6),
            _leg("B", "USDC", 1e6, 1.03e6)]
    op = evaluate_cycle(legs, gas_usd=0.05)
    assert op.path == ["USDC", "A", "B", "USDC"]
    assert abs(op.net_profit - (op.gross_profit - 0.05)) < 1e-9
    assert op.net_profit > 0


def test_gas_alto_mata_fresta_pequena():
    # fresta minúscula (0.2% na última perna): gás de Ethereum devora
    legs = [_leg("USDC", "A", 1e6, 1e6), _leg("A", "B", 1e6, 1e6),
            _leg("B", "USDC", 1e6, 1.002e6)]
    barato = evaluate_cycle(legs, gas_usd=0.05)
    caro = evaluate_cycle(legs, gas_usd=25.0)
    assert caro.net_profit < barato.net_profit
    assert caro.net_profit < 0


def test_simulate_cycle_perna_seca():
    # pool sem reserva de saída -> ciclo morre em 0
    legs = [_leg("USDC", "A", 1e6, 0.0)]
    assert simulate_cycle(1000, legs) == 0.0


def test_cycle_edge_neutro_e_negativo_pela_taxa():
    # loop 1:1:1 com 0.3% por perna -> borda ~ -(3*0.3%) = -0.9%
    legs = [_leg("USDC", "A", 1e6, 1e6), _leg("A", "B", 1e6, 1e6),
            _leg("B", "USDC", 1e6, 1e6)]
    edge = cycle_edge(legs)
    assert -0.0095 < edge < -0.0085          # perto de -0.9%


def test_cycle_edge_positivo_quando_ha_fresta():
    legs = [_leg("USDC", "A", 1e6, 1e6), _leg("A", "B", 1e6, 1e6),
            _leg("B", "USDC", 1e6, 1.03e6)]
    assert cycle_edge(legs) > 0              # a borda detecta a fresta


def test_borda_positiva_bate_com_lucro_do_otimizador():
    # se a borda é positiva, o otimizador acha entrada > 0 e lucro > 0
    legs = [_leg("USDC", "A", 1e6, 1e6), _leg("A", "B", 1e6, 1e6),
            _leg("B", "USDC", 1e6, 1.03e6)]
    assert cycle_edge(legs) > 0
    x, gross = optimize_cycle(legs)
    assert x > 0 and gross > 0


def test_flash_fee_reduz_a_borda():
    legs = [_leg("USDC", "A", 1e6, 1e6), _leg("A", "B", 1e6, 1e6),
            _leg("B", "USDC", 1e6, 1.03e6)]
    assert cycle_edge(legs, flash_fee_bps=0) > cycle_edge(legs, flash_fee_bps=50)


def test_evaluate_cycle_expoe_a_borda():
    legs = [_leg("USDC", "A", 1e6, 1e6), _leg("A", "B", 1e6, 1e6),
            _leg("B", "USDC", 1e6, 1.03e6)]
    op = evaluate_cycle(legs, gas_usd=0.03, flash_fee_bps=5)
    assert op.edge > 0 and op.net_profit > 0
