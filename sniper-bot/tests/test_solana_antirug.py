"""Testes das proteções anti-rug (round-trip, holders, decisão de saída)."""

from types import SimpleNamespace

import pytest

from solana_sniper import rugcheck
from solana_sniper.config import WSOL_MINT
from solana_sniper.monitor import decide_exit


def _cfg(**kw):
    base = dict(
        slippage_bps=100, max_roundtrip_loss_pct=0.20, max_top_holder_pct=0.0,
        use_trailing=True, trailing_pct=0.20, take_profit_pct=0.50,
        stop_loss_pct=0.30, time_stop_sec=300, liq_drop_pct=0.40,
        monitor_interval_sec=3.0,
    )
    base.update(kw)
    return SimpleNamespace(**base)


# ---- Simulação de venda (round-trip) ----

def test_roundtrip_token_vendavel(monkeypatch):
    # compra 1e9 -> 1000 tokens; vende 1000 -> 0.95e9 (perde 5%)
    quotes = iter([{"outAmount": "1000"}, {"outAmount": str(int(0.95e9))}])
    monkeypatch.setattr(rugcheck, "get_quote", lambda *a, **k: next(quotes))
    rt = rugcheck.simulate_round_trip(int(1e9), "Mint", 100)
    assert rt["sellable"] and abs(rt["loss_pct"] - 0.05) < 1e-9


def test_roundtrip_honeypot_sem_rota_de_venda(monkeypatch):
    def fake_quote(inp, out, amount, slippage):
        if inp == WSOL_MINT:
            return {"outAmount": "1000"}      # compra ok
        raise RuntimeError("no route")        # venda impossível
    monkeypatch.setattr(rugcheck, "get_quote", fake_quote)
    rt = rugcheck.simulate_round_trip(int(1e9), "Mint", 100)
    assert rt["sellable"] is False and "honeypot" in rt["reason"]


def test_roundtrip_sem_rota_de_compra(monkeypatch):
    def fake_quote(*a, **k):
        raise RuntimeError("no route")   # token novo demais, fora do Jupiter
    monkeypatch.setattr(rugcheck, "get_quote", fake_quote)
    rt = rugcheck.simulate_round_trip(int(1e9), "Mint", 100)
    assert rt["sellable"] is False and "compra" in rt["reason"]


def test_assess_reprova_perda_alta(monkeypatch):
    # vende de volta só metade -> perde 50% > limite 20%
    quotes = iter([{"outAmount": "1000"}, {"outAmount": str(int(0.5e9))}])
    monkeypatch.setattr(rugcheck, "get_quote", lambda *a, **k: next(quotes))
    v = rugcheck.assess_pre_buy(None, "Mint", _cfg(max_roundtrip_loss_pct=0.20), int(1e9))
    assert not v.ok and any("ida-e-volta" in r for r in v.reasons)


def test_assess_aprova_token_ok(monkeypatch):
    quotes = iter([{"outAmount": "1000"}, {"outAmount": str(int(0.95e9))}])
    monkeypatch.setattr(rugcheck, "get_quote", lambda *a, **k: next(quotes))
    v = rugcheck.assess_pre_buy(None, "Mint", _cfg(), int(1e9))
    assert v.ok and v.reasons == []


# ---- Concentração de holders ----

class FakeRPC:
    def __init__(self, supply, top):
        self._supply = supply
        self._top = top

    def get_token_supply(self, mint):
        return {"value": {"amount": str(self._supply)}}

    def get_token_largest_accounts(self, mint):
        return {"value": [{"amount": str(self._top)}]}


def test_holder_concentration(monkeypatch):
    monkeypatch.setattr(rugcheck, "get_quote", lambda *a, **k: {"outAmount": "1000"})
    rpc = FakeRPC(supply=1000, top=600)   # 60% numa carteira
    v = rugcheck.assess_pre_buy(rpc, "Mint", _cfg(max_top_holder_pct=0.30), int(1e9))
    assert not v.ok and any("maior holder" in r for r in v.reasons)


# ---- Decisão de saída (auto-exit) ----

def test_exit_take_profit():
    assert decide_exit(100, 150, 145, 150, 10, _cfg()) == (True, "take_profit")


def test_exit_stop_loss():
    # sem trailing, para isolar o stop-loss (entry 100, sl 30% -> sai em 70)
    assert decide_exit(100, 100, 75, 70, 10, _cfg(use_trailing=False)) == (True, "stop_loss")


def test_exit_trailing():
    # pico 200, recuo de 20% -> sai em 160 ou abaixo
    assert decide_exit(100, 200, 170, 159, 10, _cfg(take_profit_pct=5.0)) == (True, "trailing")


def test_exit_time_stop():
    assert decide_exit(100, 110, 105, 105, 301, _cfg(use_trailing=False,
                       take_profit_pct=5.0)) == (True, "time_stop")


def test_exit_liquidity_drop():
    # valor caiu 50% entre checagens (>40%) -> venda de emergência
    assert decide_exit(100, 120, 120, 60, 5, _cfg()) == (True, "liquidity_drop")


def test_exit_segura_posicao():
    # nada disparou: mantém aberta
    assert decide_exit(100, 110, 108, 110, 10, _cfg(take_profit_pct=5.0)) == (False, None)


# ---- Loop assíncrono de monitoramento ----

def test_manage_position_vende_no_take_profit(monkeypatch):
    import asyncio

    from solana_sniper import monitor

    monkeypatch.setattr(monitor, "get_quote", lambda *a, **k: {"outAmount": "160"})
    sold = {}

    def fake_swap(rpc, wallet, cfg, inp, out, amount):
        sold["amount"] = amount
        return {"signature": "SIG"}

    monkeypatch.setattr(monitor, "execute_swap", fake_swap)

    async def no_sleep(_):
        return None

    ticks = [0]

    def clock():
        ticks[0] += 1
        return ticks[0]

    res = asyncio.run(monitor.manage_position(
        None, None, _cfg(), "Mint", 1000, 100, clock=clock, sleep=no_sleep))
    assert res["reason"] == "take_profit"
    assert res["signature"] == "SIG"
    assert sold["amount"] == 1000        # vendeu todos os tokens
    assert res["pnl_lamports"] == 60     # 160 - 100
