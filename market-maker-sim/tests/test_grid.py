"""Testes do simulador de GRID de futuros."""

from mmsim.grid import GridParams, _crash, _levels, _ranging, simulate_grid


def test_levels_dentro_da_faixa():
    lv = _levels(GridParams(90, 110, 10))
    assert lv[0] == 90 and abs(lv[-1] - 110) < 1e-9   # começa no piso, acaba no teto
    assert len(lv) == 11                              # n_grids + 1 níveis
    assert all(lv[i] < lv[i + 1] for i in range(10))  # crescentes


def test_mercado_de_lado_da_lucro_sem_liquidar():
    st = simulate_grid(_ranging(), GridParams(96, 104, 30, 2, 100))
    assert not st["liquidated"]
    assert st["net"] > 0            # colhe a oscilação dentro da faixa
    assert st["fills"] > 0


def test_crash_com_alavancagem_baixa_sobrevive_mas_perde():
    st = simulate_grid(_crash(), GridParams(70, 110, 30, 2, 100))
    assert not st["liquidated"]     # 2x aguenta o tranco
    assert st["net"] < 0            # tendência de baixa -> acumula estoque perdedor


def test_crash_com_alavancagem_alta_liquida():
    st = simulate_grid(_crash(), GridParams(70, 110, 30, 5, 100))
    assert st["liquidated"]         # 5x quebra quando o preço rompe a faixa
    assert st["final_equity"] == 0.0
    assert st["return_pct"] <= -100.0


def test_faixa_larga_demais_quase_nao_executa():
    # faixa gigante longe do preço: os níveis não são tocados
    st = simulate_grid(_ranging(), GridParams(1000, 2000, 30, 2, 100))
    assert st["fills"] == 0
    assert st["net"] == 0.0
