"""Testes do diário de operações (parte pura)."""

from bybit_bot.journal import by_strategy, pnl_pct, strategy_of, summarize


def test_strategy_of_classifica_por_side_e_note():
    assert strategy_of({"side": "short", "note": "grid short 2x"}) == "Short baixa alav. (2-3x)"
    assert strategy_of({"side": "short", "note": "grid 3x"}) == "Short baixa alav. (2-3x)"
    assert strategy_of({"side": "short", "note": "grid 10x trailing"}) == "Alavancagem 10x"
    assert strategy_of({"side": "long", "note": "LONG 10x"}) == "Alavancagem 10x"
    assert strategy_of({"side": "neutro", "note": "grid neutro 2x"}) == "Neutro"
    assert strategy_of({"side": "long", "note": "GANHO DUPLO produto estruturado"}) == "Ganho Duplo (avulso)"


def test_by_strategy_separa_sorte_avulsa_do_que_se_repete():
    trades = [
        {"side": "short", "note": "grid short 2x", "result": "20.0"},
        {"side": "short", "note": "grid 2x", "result": "30.0"},
        {"side": "long", "note": "GANHO DUPLO estruturado", "result": "300.0"},
        {"side": "neutro", "note": "grid neutro", "result": "-6.0"},
    ]
    rows = by_strategy(trades)
    nomes = [name for name, _ in rows]
    # ordenado do maior resultado pro menor: Ganho Duplo (300) na frente
    assert nomes[0] == "Ganho Duplo (avulso)"
    short = dict(rows)["Short baixa alav. (2-3x)"]
    assert short["n"] == 2 and abs(short["total"] - 50.0) < 1e-9   # os dois shorts juntos
    assert dict(rows)["Neutro"]["total"] == -6.0


def test_pnl_pct_long_e_short():
    assert abs(pnl_pct("long", 100, 110) - 0.10) < 1e-9     # long sobe -> ganha
    assert abs(pnl_pct("short", 100, 90) - 0.10) < 1e-9     # short cai -> ganha
    assert abs(pnl_pct("short", 100, 110) + 0.10) < 1e-9    # short sobe -> perde
    assert pnl_pct("long", 0, 10) == 0.0                    # entrada inválida
    assert pnl_pct("neutro", 100, 130) == 0.0              # neutro não é direcional


def test_summarize_conta_acertos_e_total():
    trades = [{"result": "3.0"}, {"result": "-1.0"}, {"result": "2.0"}, {"result": ""}]
    s = summarize(trades)
    assert s["n"] == 3                      # ignora o vazio
    assert s["wins"] == 2 and s["losses"] == 1
    assert abs(s["win_rate"] - 2 / 3) < 1e-9
    assert abs(s["total"] - 4.0) < 1e-9
    assert abs(s["expectancy"] - 4.0 / 3) < 1e-9


def test_summarize_vazio():
    s = summarize([])
    assert s["n"] == 0 and s["total"] == 0.0 and s["win_rate"] == 0.0
