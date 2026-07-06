"""Testes da simulação de arbitragem (a parte que diz se dá lucro DE VERDADE)."""

from flashsim.simulate import Pool, find_arbitrage, _one_way


def test_sem_diferenca_nao_ha_lucro():
    # duas pools idênticas -> nenhum gap -> lucro líquido negativo (só custa gás)
    p = Pool("DEX-A", usdc=1_000_000, token=1_000_000, fee_bps=30)
    q = Pool("DEX-B", usdc=1_000_000, token=1_000_000, fee_bps=30)
    op = find_arbitrage("TOKEN/USDC", p, q, flash_fee_bps=5, gas_usd=0.05)
    assert op.net_profit < 0
    assert op.spread_pct < 1e-6


def test_gap_grande_da_lucro_com_gas_barato():
    # p2 tem token mais escasso -> token vale mais em p2 -> compra na p1, vende na p2
    p1 = Pool("DEX-A", usdc=1_000_000, token=1_000_000, fee_bps=30)  # preço 1.0
    p2 = Pool("DEX-B", usdc=1_000_000, token=960_000, fee_bps=30)    # ~4% mais caro
    op = find_arbitrage("TOKEN/USDC", p1, p2, flash_fee_bps=5, gas_usd=0.05)
    assert op.spread_pct > 3
    assert op.buy_dex == "DEX-A" and op.sell_dex == "DEX-B"
    assert op.net_profit > 0
    assert op.borrow_usdc > 0


def test_mesmo_gap_morre_com_gas_caro():
    # MESMO gap, mas gás caro (Ethereum): o lucro vira prejuízo -> a lição honesta
    p1 = Pool("DEX-A", usdc=100_000, token=100_000, fee_bps=30)
    p2 = Pool("DEX-B", usdc=100_000, token=99_500, fee_bps=30)       # gap pequeno ~0.5%
    barato = find_arbitrage("T/USDC", p1, p2, flash_fee_bps=5, gas_usd=0.05)
    caro = find_arbitrage("T/USDC", p1, p2, flash_fee_bps=5, gas_usd=40.0)
    assert caro.net_profit < barato.net_profit
    assert caro.net_profit < 0            # gás de Ethereum come o gap pequeno


def test_taxa_das_dex_reduz_o_gap_util():
    # gap de 'vitrine' de ~1%, mas 0.3%+0.3% de taxa das DEXs come boa parte
    p1 = Pool("DEX-A", usdc=1_000_000, token=1_000_000, fee_bps=30)
    p2 = Pool("DEX-B", usdc=1_000_000, token=990_000, fee_bps=30)    # ~1%
    op = find_arbitrage("T/USDC", p1, p2, flash_fee_bps=5, gas_usd=0.05)
    # lucro líquido é bem menor que 1% do valor emprestado (as taxas comem)
    assert op.net_profit < 0.01 * op.borrow_usdc


def test_one_way_pico_existe():
    # o lucro sobe e depois cai com o tamanho do empréstimo (tem um ótimo no meio)
    p1 = Pool("A", usdc=1_000_000, token=1_000_000, fee_bps=30)
    p2 = Pool("B", usdc=1_000_000, token=950_000, fee_bps=30)
    small = _one_way(1_000, p1, p2, 5)
    mid = _one_way(20_000, p1, p2, 5)
    huge = _one_way(400_000, p1, p2, 5)
    assert mid > small and mid > huge
