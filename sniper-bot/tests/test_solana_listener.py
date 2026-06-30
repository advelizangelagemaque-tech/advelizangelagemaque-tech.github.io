"""Testes da detecção automática de tokens novos (parsing, sem rede)."""

import pytest

from solana_sniper.config import WSOL_MINT
from solana_sniper.listener import (PROGRAMS, PoolListener, extract_mint_from_tx,
                                    is_create_event, mint_from_notification,
                                    ws_url_from_rpc)

PUMP_MARKERS = PROGRAMS["pump"]["markers"]


class FakeRPC:
    def __init__(self, tx):
        self._tx = tx
        self.calls = []

    def get_transaction(self, signature):
        self.calls.append(signature)
        return self._tx


def _tx_with_mint(mint):
    return {"meta": {"postTokenBalances": [
        {"mint": WSOL_MINT}, {"mint": mint},
    ]}}


def test_ws_url_conversao():
    assert ws_url_from_rpc("https://api.devnet.solana.com") == "wss://api.devnet.solana.com"
    assert ws_url_from_rpc("http://localhost:8899") == "ws://localhost:8899"


def test_is_create_event():
    assert is_create_event(["Program log: Instruction: Create"], PUMP_MARKERS)
    assert not is_create_event(["Program log: Instruction: Buy"], PUMP_MARKERS)
    assert not is_create_event([], PUMP_MARKERS)


def test_extract_mint_ignora_wsol():
    assert extract_mint_from_tx(_tx_with_mint("TokenMint123")) == "TokenMint123"
    # só wSOL -> nada
    assert extract_mint_from_tx({"meta": {"postTokenBalances": [{"mint": WSOL_MINT}]}}) is None
    assert extract_mint_from_tx({}) is None


def _notif(logs, sig="sig123", err=None):
    return {"method": "logsNotification", "params": {"result": {"value": {
        "logs": logs, "signature": sig, "err": err,
    }}}}


def test_mint_from_notification_feliz():
    rpc = FakeRPC(_tx_with_mint("NewToken999"))
    got = mint_from_notification(rpc, _notif(["Program log: Instruction: Create"]), PUMP_MARKERS)
    assert got == ("NewToken999", "sig123")
    assert rpc.calls == ["sig123"]


def test_mint_from_notification_ignora_nao_create():
    rpc = FakeRPC(_tx_with_mint("X"))
    assert mint_from_notification(rpc, _notif(["Instruction: Buy"]), PUMP_MARKERS) is None
    assert rpc.calls == []   # nem busca a tx


def test_mint_from_notification_ignora_erro():
    rpc = FakeRPC(_tx_with_mint("X"))
    notif = _notif(["Instruction: Create"], err={"InstructionError": []})
    assert mint_from_notification(rpc, notif, PUMP_MARKERS) is None


def test_mint_from_notification_ignora_outra_mensagem():
    rpc = FakeRPC(_tx_with_mint("X"))
    assert mint_from_notification(rpc, {"method": "subscribed"}, PUMP_MARKERS) is None


def test_listener_programa_invalido():
    with pytest.raises(ValueError):
        PoolListener(FakeRPC({}), "wss://x", program="ethereum")
