"""Testes da simulação de market making."""

from mmsim.demo import _candles_ranging, _candles_trending
from mmsim.mm import MMParams, simulate_mm


def _p(**kw):
    base = dict(spread_bps=10, order_size=20, max_inventory=100, maker_fee_bps=2)
    base.update(kw)
    return MMParams(**base)


def test_mercado_de_lado_da_lucro():
    st = simulate_mm(_candles_ranging(), _p())
    assert st["net"] > 0                       # colhe o spread na oscilação
    assert st["round_trips"] > 0
    assert abs(st["end_inventory_usdt"]) < 100 # estoque controlado


def test_tendencia_maltrata_o_estoque():
    st = simulate_mm(_candles_trending(), _p())
    # preço só sobe -> a gente vende (short) e fica com estoque negativo -> prejuízo
    assert st["end_inventory_usdt"] < 0
    assert st["net"] < simulate_mm(_candles_ranging(), _p())["net"]


def test_spread_largo_nao_executa():
    # spread gigante (50%): o preço nunca toca as ordens -> nada acontece
    st = simulate_mm(_candles_ranging(), _p(spread_bps=5000))
    assert st["buys"] == 0 and st["sells"] == 0 and st["net"] == 0.0


def test_taxa_reduz_o_lucro():
    sem = simulate_mm(_candles_ranging(), _p(maker_fee_bps=0))
    com = simulate_mm(_candles_ranging(), _p(maker_fee_bps=5))
    assert com["net"] < sem["net"]


def test_uma_ida_e_volta_captura_o_spread():
    # candle que sobe e desce o bastante para tocar compra E venda
    candles = [[0, 100.0, 100.0, 100.0, 100.0, 1],
               [1, 100.0, 100.5, 99.5, 100.0, 1],   # toca bid (99.95) e ask (100.05)
               [2, 100.0, 100.0, 100.0, 100.0, 1]]
    st = simulate_mm(candles, _p(maker_fee_bps=0))
    assert st["buys"] == 1 and st["sells"] == 1
    assert st["net"] > 0                        # comprou barato, vendeu caro
