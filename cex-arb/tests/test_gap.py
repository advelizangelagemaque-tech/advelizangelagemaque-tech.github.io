"""Testes da matemática de arbitragem entre corretoras."""

from cexarb.gap import Book, compute_gap, net_arb


def test_sem_gap_da_prejuizo():
    # livros iguais: o gap de vitrine é 0, e as taxas tornam o real negativo
    a = Book("bybit", bid=100.0, ask=100.1)
    b = Book("binance", bid=100.0, ask=100.1)
    g = compute_gap("X/USDT", a, b, 0.001, 0.001)
    assert not g.profitable
    assert g.net_pct < 0


def test_gap_de_vitrine_engana():
    # 'vitrine' parece 0.3% mas, cruzando o livro + taxas (0.2%), o real some
    a = Book("bybit", bid=99.9, ask=100.0)     # meio ~99.95
    b = Book("binance", bid=100.2, ask=100.3)  # meio ~100.25  -> vitrine ~0.30%
    g = compute_gap("X/USDT", a, b, 0.001, 0.001)
    assert g.displayed_gap_pct > 0.25
    # compra na Bybit (ask 100.0) e vende na Binance (bid 100.2): bruto 0.2%,
    # menos 0.2% de taxa -> praticamente zero (real << vitrine)
    assert g.net_pct < g.displayed_gap_pct
    assert g.net_pct < 0.05


def test_gap_grande_da_lucro():
    # gap grande de verdade: barato na Bybit, caro na Binance
    a = Book("bybit", bid=99.0, ask=99.1)
    b = Book("binance", bid=101.0, ask=101.1)   # ~2% acima
    g = compute_gap("X/USDT", a, b, 0.001, 0.001)
    assert g.profitable
    assert g.buy_ex == "bybit" and g.sell_ex == "binance"
    assert g.net_usd_per_1k > 0


def test_direcao_inversa():
    # caro na Bybit, barato na Binance -> compra na Binance, vende na Bybit
    a = Book("bybit", bid=101.0, ask=101.1)
    b = Book("binance", bid=99.0, ask=99.1)
    buy, sell, net = net_arb(a, b, 0.001, 0.001)
    assert buy == "binance" and sell == "bybit"
    assert net > 0


def test_taxa_alta_mata_o_lucro():
    a = Book("bybit", bid=99.9, ask=100.0)
    b = Book("binance", bid=100.5, ask=100.6)   # ~0.55% de vitrine
    barato = compute_gap("X/USDT", a, b, 0.001, 0.001)    # 0.1%+0.1%
    caro = compute_gap("X/USDT", a, b, 0.004, 0.004)      # 0.4%+0.4%
    assert caro.net_pct < barato.net_pct
    assert not caro.profitable
