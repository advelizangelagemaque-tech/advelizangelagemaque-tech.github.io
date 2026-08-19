"""Testes do detector de rollover (setup de short)."""

from bybit_bot.short_setup import detect_short_setup


def _candles_from_closes(closes):
    # candle [ts,o,h,l,c,v] com high/low simples ao redor do fechamento
    out = []
    prev = closes[0]
    for i, c in enumerate(closes):
        out.append([i, prev, max(prev, c) * 1.001, min(prev, c) * 0.999, c, 1])
        prev = c
    return out


def test_ainda_subindo_nao_shorta():
    # só sobe até o fim -> esticado mas de pé -> NÃO shortar (armadilha)
    closes = [100 * (1.03 ** i) for i in range(30)]
    d = detect_short_setup(_candles_from_closes(closes))
    assert d["pumped"] and not d["rolling"]
    assert d["light"] == "wait"
    assert "NÃO SHORTAR" in d["verdict"]


def test_rollover_confirmado_vira_short_valido():
    # sobe forte e depois cai vários candles -> rollover -> SHORT VÁLIDO
    up = [100 * (1.03 ** i) for i in range(20)]
    down = [up[-1] * (0.97 ** i) for i in range(1, 12)]
    d = detect_short_setup(_candles_from_closes(up + down))
    assert d["light"] == "short"
    assert d["pumped"] and d["pulled_back"] and d["below_fast"] and d["momentum_down"]
    assert "SHORT VÁLIDO" in d["verdict"]


def test_ja_desabou_nao_shorta():
    # pumpou e DESABOU forte (RSI no fundo) -> tarde demais, escudo anti-fundo
    up = [100 * (1.05 ** i) for i in range(12)]
    crash = [up[-1] * (0.90 ** i) for i in range(1, 14)]     # queda violenta -> RSI baixo
    d = detect_short_setup(_candles_from_closes(up + crash))
    assert not d["not_oversold"]           # RSI já no fundo
    assert d["light"] != "short"           # não dispara short atrasado


def test_caiu_demais_do_topo_nao_shorta():
    # pumpou e caiu ~45% do topo, mas RSI ainda razoável -> tarde (caiu demais)
    up = [100 * (1.05 ** i) for i in range(14)]
    # queda controlada até ~-45% do topo, sem esmagar o RSI ao fundo
    top = up[-1]
    down = [top * (1 - 0.06 * i) for i in range(1, 9)]      # -6% por candle ~ -48%
    d = detect_short_setup(_candles_from_closes([100] * 20 + up + down))
    assert not d["not_too_deep"]            # caiu demais do topo
    assert d["light"] != "short"


def test_mercado_de_lado_sem_setup():
    # de lado, sem pump -> SEM SETUP
    closes = [100 + (i % 3) for i in range(30)]
    d = detect_short_setup(_candles_from_closes(closes))
    assert not d["pumped"]
    assert d["light"] == "none"
    assert "SEM SETUP" in d["verdict"]


def test_stop_fica_acima_do_preco_no_short():
    up = [100 * (1.03 ** i) for i in range(20)]
    down = [up[-1] * (0.97 ** i) for i in range(1, 12)]
    d = detect_short_setup(_candles_from_closes(up + down))
    assert d["recent_high"] > d["price"]          # stop sugerido é acima
    assert d["dist_stop_pct"] > 0
