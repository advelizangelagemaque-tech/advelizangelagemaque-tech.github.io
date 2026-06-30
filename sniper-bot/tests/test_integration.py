"""Teste de integração ponta a ponta do loop principal (paper, sem rede).

Exercita: detecção -> filtro de qualidade -> entrada (paper) -> acompanhamento
de TP -> gravação no diário -> resumo. Tudo com um cliente simulado.
"""

import csv

from sniper import main as main_mod
from sniper.summary import summarize
from tests.conftest import exchange_info, make_cfg


class ScriptedClient:
    """Cliente simulado: na 1ª consulta só tem BTC; depois surge NEWUSDT.
    O preço sobe de 2.0 (entrada) para 2.5 (bate o take-profit)."""

    def __init__(self):
        self._info_calls = 0
        self._prices = iter([2.0, 2.5])  # entrada, depois resolução
        self._last_price = 2.5

    def exchange_info(self):
        self._info_calls += 1
        symbols = ["BTCUSDT"] if self._info_calls == 1 else ["BTCUSDT", "NEWUSDT"]
        return exchange_info(symbols)

    def mark_price(self, symbol):
        try:
            self._last_price = next(self._prices)
        except StopIteration:
            pass
        return {"markPrice": str(self._last_price)}

    def depth(self, symbol, limit):
        return {"bids": [["1.99", "1000"]], "asks": [["2.00", "1000"]]}


def test_fluxo_completo_paper_gera_win(tmp_path, monkeypatch):
    journal_path = str(tmp_path / "trades.csv")
    monkeypatch.setattr(main_mod, "make_client", lambda *a, **k: ScriptedClient())

    cfg = make_cfg(max_trades=1, poll_interval_ms=100, margin_usdt=20, leverage=3)
    # run() termina sozinho ao fechar a posição (max_trades atingido e livro vazio).
    main_mod.run(cfg, mode_trade="paper", detect_mode="poll", side="BUY",
                 journal_path=journal_path)

    with open(journal_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    status = [r["status"] for r in rows]
    assert "OPEN" in status and "WIN" in status

    s = summarize(journal_path)
    assert s["wins"] == 1 and s["losses"] == 0
    assert s["total_pnl"] > 0   # entrou a 2.0, saiu no TP 2.2
