"""Testes das travas de segurança do pump.fun (PumpPortal-local)."""

from types import SimpleNamespace

import pytest

from solana_sniper import pumpfun
from solana_sniper.pumpfun import only_signer_is, spend_within_limit

solders = pytest.importorskip("solders")
from solders.keypair import Keypair                     # noqa: E402
from solders.hash import Hash                           # noqa: E402
from solders.message import MessageV0                   # noqa: E402
from solders.signature import Signature                 # noqa: E402
from solders.system_program import transfer, TransferParams  # noqa: E402
from solders.transaction import VersionedTransaction    # noqa: E402


def _unsigned_tx(payer: Keypair, ixs) -> bytes:
    msg = MessageV0.try_compile(payer.pubkey(), ixs, [], Hash.default())
    return bytes(VersionedTransaction.populate(msg, [Signature.default()]))


def _tx_for(kp: Keypair) -> bytes:
    ix = transfer(TransferParams(from_pubkey=kp.pubkey(),
                                 to_pubkey=Keypair().pubkey(), lamports=1))
    return _unsigned_tx(kp, [ix])


def _cfg(**kw):
    base = dict(max_spend_sol=0.05, slippage_bps=100, priority_fee_sol=0.00005,
                network="mainnet", allow_mainnet=False)
    base.update(kw)
    return SimpleNamespace(**base)


# ---- helpers puros ----

def test_spend_within_limit_ok():
    ok, spent = spend_within_limit(int(0.1e9), int(0.089e9), 0.01)
    assert ok and spent == pytest.approx(0.011e9, abs=1000)


def test_spend_within_limit_drenagem():
    ok, spent = spend_within_limit(int(0.6e9), int(0.1e9), 0.01)
    assert not ok and spent == pytest.approx(0.5e9, abs=1000)


def test_only_signer_is():
    kp = Keypair()
    raw = _tx_for(kp)
    assert only_signer_is(raw, str(kp.pubkey()))
    assert not only_signer_is(raw, str(Keypair().pubkey()))


# ---- trade() com as travas ----

class _FakeRPC:
    def __init__(self, pre, post):
        self._pre, self._post = pre, post

    def get_balance(self, pk):
        return {"value": self._pre}

    def call(self, method, params):
        assert method == "simulateTransaction"
        return {"value": {"err": None, "logs": [],
                          "accounts": [{"lamports": self._post}]}}


def test_trade_simula_ok(monkeypatch):
    kp = Keypair()
    monkeypatch.setattr(pumpfun, "request_trade_tx", lambda *a, **k: _tx_for(kp))
    wallet = SimpleNamespace(secret=bytes(kp))
    rpc = _FakeRPC(pre=int(1e9), post=int(0.988e9))   # gastou 0.012 SOL
    res = pumpfun.trade(rpc, wallet, _cfg(), "buy", "MintX", 0.01, send_it=False)
    assert res["simulated"] and not res["sent"]


def test_trade_recusa_drenagem(monkeypatch):
    kp = Keypair()
    monkeypatch.setattr(pumpfun, "request_trade_tx", lambda *a, **k: _tx_for(kp))
    wallet = SimpleNamespace(secret=bytes(kp))
    rpc = _FakeRPC(pre=int(1e9), post=int(0.1e9))      # gastou 0.9 SOL comprando 0.01
    with pytest.raises(RuntimeError, match="drenagem"):
        pumpfun.trade(rpc, wallet, _cfg(), "buy", "MintX", 0.01, send_it=False)


def test_trade_respeita_teto(monkeypatch):
    kp = Keypair()
    wallet = SimpleNamespace(secret=bytes(kp))
    with pytest.raises(ValueError, match="teto"):
        pumpfun.trade(None, wallet, _cfg(max_spend_sol=0.05), "buy", "MintX", 1.0, send_it=False)


def test_trade_recusa_outros_assinantes(monkeypatch):
    kp = Keypair()
    outra = Keypair()
    # transação cujo pagador/assinante é OUTRA carteira, não a nossa
    monkeypatch.setattr(pumpfun, "request_trade_tx", lambda *a, **k: _tx_for(outra))
    wallet = SimpleNamespace(secret=bytes(kp))
    rpc = _FakeRPC(pre=int(1e9), post=int(0.99e9))
    with pytest.raises(RuntimeError, match="assinantes"):
        pumpfun.trade(rpc, wallet, _cfg(), "buy", "MintX", 0.01, send_it=False)
