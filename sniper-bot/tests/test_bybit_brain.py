"""Testes do 'cérebro' (gestão de risco automática)."""

from types import SimpleNamespace

from bybit_bot.brain import consec_losses, decide, drawdown_ok, rolling_pf


def _cfg(**kw):
    base = dict(brain_min_trades=8, brain_reduce_pf=1.0, brain_pause_pf=0.6,
                brain_pause_streak=5)
    base.update(kw)
    return SimpleNamespace(**base)


def test_rolling_pf():
    assert rolling_pf([2.0, -1.0, 2.0, -1.0]) == 2.0     # ganhos 4 / perdas 2
    assert rolling_pf([1.0, 2.0]) == float("inf")         # sem perdas
    assert rolling_pf([]) == 1.0


def test_consec_losses():
    assert consec_losses([2.0, -1.0, -1.0, -1.0]) == 3
    assert consec_losses([-1.0, 2.0]) == 0


def test_decide_amostra_pequena():
    d = decide([-1.0, -1.0], _cfg())
    assert d["open_allowed"] and d["margin_mult"] == 1.0    # ainda aprendendo


def test_decide_normal():
    pnls = [2.0, 2.0, -1.0, 2.0, 2.0, -1.0, 2.0, 2.0]      # PF alto
    d = decide(pnls, _cfg())
    assert d["open_allowed"] and d["margin_mult"] == 1.0


def test_decide_reduz_risco():
    # PF entre pause_pf e reduce_pf -> reduz à metade
    pnls = [2.0, -1.5, -1.5, 2.0, -1.5, 2.0, -1.5, -1.0]   # perdas ~ ganhos, PF<1
    d = decide(pnls, _cfg())
    assert d["open_allowed"] and d["margin_mult"] == 0.5


def test_decide_pausa_por_streak():
    pnls = [2.0, 2.0, 2.0, -1.0, -1.0, -1.0, -1.0, -1.0]   # 5 perdas seguidas
    d = decide(pnls, _cfg())
    assert not d["open_allowed"] and d["margin_mult"] == 0.0


def test_drawdown_breaker():
    assert drawdown_ok(90.0, 100.0, 0.12)       # caiu 10% (<12%) -> ok
    assert not drawdown_ok(85.0, 100.0, 0.12)   # caiu 15% (>12%) -> disjuntor
    assert drawdown_ok(100.0, 0.0, 0.12)        # sem topo ainda -> ok


def test_exposure_for_drawdown():
    from bybit_bot.brain import exposure_for_drawdown
    # sem queda -> exposição cheia
    d = exposure_for_drawdown(0.02, 0.05, 0.12)
    assert d["mult"] == 1.0 and not d["flatten"]
    # queda média -> metade
    d = exposure_for_drawdown(0.07, 0.05, 0.12)
    assert d["mult"] == 0.5 and not d["flatten"]
    # queda forte -> caixa (disjuntor)
    d = exposure_for_drawdown(0.15, 0.05, 0.12)
    assert d["mult"] == 0.0 and d["flatten"]
