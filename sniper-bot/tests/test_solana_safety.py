"""Testes das checagens de segurança da Solana (sem rede)."""

import json
import os

import pytest

from solana_sniper.safety import check_token_safety
from solana_sniper.wallet import guard_network, load_burner
from solana_sniper.execute import execute_swap


class FakeRPC:
    def __init__(self, result):
        self._result = result

    def get_account_info(self, pubkey):
        return self._result


def _mint(mint_authority=None, freeze_authority=None):
    return {"value": {"data": {"parsed": {
        "type": "mint",
        "info": {
            "mintAuthority": mint_authority,
            "freezeAuthority": freeze_authority,
            "decimals": 9, "supply": "1000000",
        },
    }}}}


def test_token_seguro_sem_autoridades():
    r = check_token_safety(FakeRPC(_mint(None, None)), "Mint111")
    assert r.ok and r.reasons == []


def test_freeze_authority_reprova():
    r = check_token_safety(FakeRPC(_mint(None, "Freeze111")), "Mint111")
    assert not r.ok
    assert any("freeze" in x.lower() for x in r.reasons)


def test_mint_authority_reprova():
    r = check_token_safety(FakeRPC(_mint("MintAuth", None)), "Mint111")
    assert not r.ok
    assert any("inflar" in x.lower() for x in r.reasons)


def test_conta_inexistente():
    with pytest.raises(ValueError):
        check_token_safety(FakeRPC({"value": None}), "Mint111")


def test_guard_bloqueia_mainnet():
    with pytest.raises(PermissionError):
        guard_network("mainnet", allow_mainnet=False)
    guard_network("mainnet", allow_mainnet=True)   # liberado de propósito
    guard_network("devnet", allow_mainnet=False)   # devnet sempre ok


def test_guard_network_invalida():
    with pytest.raises(ValueError):
        guard_network("ethereum", allow_mainnet=True)


def test_load_burner_arquivo_inexistente():
    with pytest.raises(FileNotFoundError):
        load_burner("/caminho/que/nao/existe/burner.json")


def test_load_burner_permissao_aberta(tmp_path):
    p = tmp_path / "burner.json"
    p.write_text(json.dumps([1] * 64))
    os.chmod(p, 0o644)            # permissão aberta -> deve recusar
    with pytest.raises(PermissionError):
        load_burner(str(p))


def test_load_burner_ok(tmp_path):
    p = tmp_path / "burner.json"
    p.write_text(json.dumps([1] * 64))
    os.chmod(p, 0o600)
    w = load_burner(str(p))
    assert w.loaded and len(w.secret) == 64


def test_execute_swap_desativado():
    with pytest.raises(NotImplementedError):
        execute_swap()
