"""Testes da estratégia DCA (preço médio na moeda #1 em alta 24h)."""

from bybit_bot.trader import dca_decision


def _d(roi, adds, tp=0.30, trig=0.50, dmax=2):
    return dca_decision(roi, adds, tp, trig, dmax)


def test_tp_fecha_no_alvo():
    assert _d(0.30, 0) == "tp"          # bateu +30%
    assert _d(0.55, 2) == "tp"          # bem acima do alvo


def test_hold_na_zona_neutra():
    assert _d(0.10, 0) == "hold"        # subindo, ainda não no alvo
    assert _d(-0.20, 0) == "hold"       # caiu um pouco, mas < gatilho
    assert _d(-0.49, 1) == "hold"       # quase no gatilho


def test_dca_quando_cai_e_ainda_pode_reforcar():
    assert _d(-0.50, 0) == "dca"        # 1º reforço
    assert _d(-0.50, 1) == "dca"        # 2º reforço
    assert _d(-0.70, 0) == "dca"        # caiu mais que o gatilho


def test_stop_quando_esgota_os_reforcos():
    assert _d(-0.50, 2) == "stop"       # já usou os 2 reforços -> corta
    assert _d(-0.80, 2) == "stop"


def test_tp_tem_prioridade_sobre_gatilho():
    # nunca deveria acontecer os dois juntos, mas o TP vem primeiro
    assert _d(0.40, 2) == "tp"


def test_adds_done_pela_margem():
    # a lógica do agente: adds_done = round(margem / entrada) - 1
    entrada = 2.0
    assert round(2.0 / entrada) - 1 == 0     # só a base
    assert round(4.0 / entrada) - 1 == 1     # 1 reforço
    assert round(6.0 / entrada) - 1 == 2     # 2 reforços


def test_roi_apos_reforco_volta_pra_perto_de_menos25():
    # base $2 a -50% (P&L -1). Reforço +$2 no preço atual: margem $4, P&L ~ -1.
    # ROI = -1/4 = -0.25 -> volta pra 'hold', precisa cair de novo p/ o próximo DCA.
    pnl, margem = -1.0, 4.0
    roi = pnl / margem
    assert abs(roi + 0.25) < 1e-9
    assert _d(roi, 1) == "hold"
