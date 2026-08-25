"""Testes do radar de pump fresco (parte pura)."""

from bybit_bot.pump_radar import detect_pump, pick_fires, pump_alert_text


def _candles(spec):
    # spec: lista de (close, volume). high/low simples ao redor do fechamento.
    out, prev = [], spec[0][0]
    for i, (c, v) in enumerate(spec):
        out.append([i, prev, max(prev, c) * 1.01, min(prev, c) * 0.99, c, v])
        prev = c
    return out


def test_pump_fresco_vira_fire():
    # 8 velas de lado + 12 subindo forte, ainda perto do topo, volume no fim
    rise = [102, 105, 108, 111, 114, 117, 120, 123, 126, 128, 129, 130]
    vols = [1, 1, 1, 1, 1, 1, 1, 1, 1, 5, 5, 5]
    spec = [(100, 1)] * 8 + list(zip(rise, vols))
    d = detect_pump(_candles(spec))
    assert d["pumped"] and d["hot"] and d["volume"]
    assert d["light"] == "fire"
    assert d["run_pct"] > 0.20 and d["vol_ratio"] > 1.5


def test_pump_que_ja_desinflou_nao_e_fire():
    # subiu a 150 e voltou pra 122: ainda 'pumped' na janela, mas longe do topo
    mid = [100, 115, 130, 145, 150, 149, 145, 138, 130, 126, 123, 122]
    vols = [1, 1, 1, 1, 1, 1, 1, 1, 1, 5, 5, 5]
    spec = [(100, 1)] * 5 + list(zip(mid, vols))
    d = detect_pump(_candles(spec))
    assert d["pumped"] and not d["hot"]     # caiu do topo -> não está fresco
    assert d["light"] != "fire"             # não entra como pump fresco


def test_mercado_de_lado_sem_pump():
    spec = [(100 + (i % 2), 1) for i in range(20)]
    d = detect_pump(_candles(spec))
    assert not d["pumped"]
    assert d["light"] == "none"


def test_pouco_historico():
    d = detect_pump(_candles([(100, 1)] * 10))
    assert d["light"] == "none"
    assert "histórico" in d["verdict"]


def test_pump_alert_text_tem_moeda_e_porcentagem():
    msg = pump_alert_text("MOG", 0.34, 4.2)
    assert "MOG" in msg
    assert "+34%" in msg
    assert "shortar" in msg          # lembra o objetivo: vigiar pra shortar o rollover


def test_pick_fires_ordena_por_forca():
    results = [
        {"symbol": "A/USDT:USDT", "light": "fire", "run_pct": 0.30},
        {"symbol": "B/USDT:USDT", "light": "warm", "run_pct": 0.25},
        {"symbol": "C/USDT:USDT", "light": "fire", "run_pct": 0.55},
        {"symbol": "D/USDT:USDT", "light": "none", "run_pct": 0.0},
    ]
    assert pick_fires(results) == ["C/USDT:USDT", "A/USDT:USDT"]   # só fires, mais forte 1º
