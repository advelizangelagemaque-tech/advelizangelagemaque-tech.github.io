"""Testes das checagens de segurança da Solana (sem rede)."""

import json
import os

import pytest

from solana_sniper.safety import check_token_safety
from solana_sniper.wallet import guard_network, load_burner
from solana_sniper import execute as ex
from types import SimpleNamespace


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


def _sol_cfg(**kw):
    base = dict(network="devnet", allow_mainnet=False, rpc_url="http://x",
                keypair_path="x", max_spend_sol=0.05, slippage_bps=100)
    base.update(kw)
    return SimpleNamespace(**base)


def test_execute_swap_dry_run_nao_envia(monkeypatch):
    monkeypatch.setattr(ex, "get_quote", lambda *a, **k: {"outAmount": "123"})
    from solana_sniper.config import WSOL_MINT
    wallet = SimpleNamespace(secret=b"\x01" * 64)
    res = ex.execute_swap(None, wallet, _sol_cfg(), WSOL_MINT, "TokenMint", 1_000_000, dry_run=True)
    assert res["sent"] is False and res["dry_run"] is True
    assert res["quote"]["outAmount"] == "123"


def test_execute_swap_respeita_teto_de_gasto(monkeypatch):
    monkeypatch.setattr(ex, "get_quote", lambda *a, **k: {"outAmount": "1"})
    from solana_sniper.config import WSOL_MINT, LAMPORTS_PER_SOL
    wallet = SimpleNamespace(secret=b"\x01" * 64)
    # teto 0.05 SOL; tentar gastar 1 SOL deve falhar
    with pytest.raises(ValueError):
        ex.execute_swap(None, wallet, _sol_cfg(max_spend_sol=0.05), WSOL_MINT,
                        "TokenMint", 1 * LAMPORTS_PER_SOL, dry_run=False)


def test_execute_swap_bloqueia_mainnet():
    from solana_sniper.config import WSOL_MINT
    wallet = SimpleNamespace(secret=b"\x01" * 64)
    with pytest.raises(PermissionError):
        ex.execute_swap(None, wallet, _sol_cfg(network="mainnet", allow_mainnet=False),
                        WSOL_MINT, "TokenMint", 1000, dry_run=True)


def test_keypair_from_secret_deriva_pubkey():
    solders = pytest.importorskip("solders")
    from solders.keypair import Keypair
    kp = Keypair()
    kp2 = ex.keypair_from_secret(bytes(kp))
    assert str(kp2.pubkey()) == str(kp.pubkey())

