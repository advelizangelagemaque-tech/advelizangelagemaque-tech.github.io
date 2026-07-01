"""Compra/venda no pump.fun via PumpPortal (local, NÃO-custodial).

Fluxo seguro:
  1. PumpPortal monta a transação (mantém-se atualizado com o pump.fun);
  2. conferimos que SÓ a sua chave assina;
  3. assinamos LOCALMENTE (a chave privada nunca sai daqui);
  4. SIMULAMOS na rede e checamos o gasto (anti-drenagem);
  5. só enviamos se `send_it=True` e o gasto estiver dentro do teto.

A chave privada é usada apenas para assinar localmente com solders.
"""

from __future__ import annotations

import base64
import json
import logging
import urllib.request

from .config import LAMPORTS_PER_SOL

log = logging.getLogger("solana_sniper.pumpfun")

PUMPPORTAL_LOCAL = "https://pumpportal.fun/api/trade-local"


# ---- PumpPortal ------------------------------------------------------------

def request_trade_tx(public_key: str, action: str, mint: str, amount: float,
                     denominated_in_sol: bool, slippage_pct: float,
                     priority_fee_sol: float, pool: str = "auto",
                     timeout: int = 15) -> bytes:
    """Pede ao PumpPortal a transação (bytes serializados). Não assina nada."""
    body = json.dumps({
        "publicKey": public_key, "action": action, "mint": mint,
        "amount": amount,
        "denominatedInSol": "true" if denominated_in_sol else "false",
        "slippage": slippage_pct, "priorityFee": priority_fee_sol, "pool": pool,
    }).encode()
    req = urllib.request.Request(
        PUMPPORTAL_LOCAL, data=body, headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    if not data or len(data) < 64:
        raise RuntimeError(f"PumpPortal devolveu resposta inesperada: {data[:200]!r}")
    return data


# ---- Assinatura e conferências (solders) -----------------------------------

def only_signer_is(tx_bytes: bytes, pubkey_str: str) -> bool:
    """True se a única chave exigida para assinar é a nossa (fee payer)."""
    from solders.transaction import VersionedTransaction
    tx = VersionedTransaction.from_bytes(tx_bytes)
    msg = tx.message
    n = msg.header.num_required_signatures
    signers = [str(k) for k in list(msg.account_keys)[:n]]
    return signers == [pubkey_str]


def sign_tx(tx_bytes: bytes, keypair) -> bytes:
    """Assina localmente a transação do PumpPortal."""
    from solders.transaction import VersionedTransaction
    tx = VersionedTransaction.from_bytes(tx_bytes)
    signed = VersionedTransaction(tx.message, [keypair])
    return bytes(signed)


def spend_within_limit(pre_lamports: int, post_lamports: int,
                       sol_amount: float, buffer_sol: float = 0.02) -> tuple[bool, int]:
    """Confere se o gasto simulado não excede o valor + folga de taxas."""
    spent = pre_lamports - post_lamports
    allowed = int((sol_amount + buffer_sol) * LAMPORTS_PER_SOL)
    return (spent <= allowed, spent)


# ---- RPC: simular e enviar -------------------------------------------------

def simulate(rpc, signed_bytes: bytes, owner_pubkey: str) -> dict:
    # replaceRecentBlockhash torna a checagem independente do blockhash (que pode
    # ter expirado); com ele, sigVerify precisa ser False.
    b64 = base64.b64encode(signed_bytes).decode()
    return rpc.call("simulateTransaction", [b64, {
        "encoding": "base64", "sigVerify": False, "replaceRecentBlockhash": True,
        "commitment": "processed",
        "accounts": {"encoding": "base64", "addresses": [owner_pubkey]},
    }])


def estimate_sell_value_sol(rpc, wallet, cfg, mint: str) -> int | None:
    """Quanto SOL (lamports) você receberia vendendo 100% do token agora.

    Faz uma venda simulada (não envia). Retorna None se não der para avaliar
    (ex.: não há tokens em carteira, ou sem rota de venda ainda).
    """
    from .execute import keypair_from_secret
    kp = keypair_from_secret(wallet.secret)
    pubkey = str(kp.pubkey())
    try:
        tx_bytes = request_trade_tx(pubkey, "sell", mint, "100%", False,
                                    cfg.slippage_bps / 100, cfg.priority_fee_sol, "auto")
    except Exception:  # noqa: BLE001
        return None
    if not only_signer_is(tx_bytes, pubkey):
        return None
    signed = sign_tx(tx_bytes, kp)
    pre = int(rpc.get_balance(pubkey).get("value", 0))
    sim = simulate(rpc, signed, pubkey)
    val = sim.get("value", {}) or {}
    if val.get("err"):
        return None
    accounts = val.get("accounts") or []
    post = int(accounts[0]["lamports"]) if accounts and accounts[0] else pre
    return post - pre  # SOL líquido recebido ao vender agora


def send(rpc, signed_bytes: bytes) -> str:
    # skipPreflight=True: já fizemos a NOSSA simulação de segurança; pular o
    # preflight da Helius evita o "BlockhashNotFound" quando o nó dela ainda não
    # viu o blockhash. A validade real é checada pelo líder ao processar a tx.
    b64 = base64.b64encode(signed_bytes).decode()
    return rpc.call("sendTransaction", [b64, {
        "encoding": "base64", "skipPreflight": True, "maxRetries": 3,
    }])


# ---- Orquestração ----------------------------------------------------------

def trade(rpc, wallet, cfg, action: str, mint: str, sol_amount: float,
          send_it: bool = False) -> dict:
    """Compra ('buy') ou vende ('sell') no pump.fun. Simula sempre; envia só se send_it."""
    from .execute import keypair_from_secret
    from .wallet import guard_network

    if action == "buy" and sol_amount > cfg.max_spend_sol:
        raise ValueError(
            f"Gasto {sol_amount} SOL excede o teto MAX_SPEND_SOL={cfg.max_spend_sol}."
        )

    kp = keypair_from_secret(wallet.secret)
    pubkey = str(kp.pubkey())
    slippage_pct = cfg.slippage_bps / 100
    denominated_in_sol = action == "buy"  # compra em SOL; venda em % de tokens

    if send_it:
        guard_network(cfg.network, cfg.allow_mainnet)  # envio real exige mainnet liberada

    attempts = 3 if send_it else 1
    last_err: Exception | None = None
    for attempt in range(attempts):
        tx_bytes = request_trade_tx(
            pubkey, action, mint, sol_amount, denominated_in_sol,
            slippage_pct, cfg.priority_fee_sol, pool="auto",
        )

        # Segurança: só a nossa chave pode assinar.
        if not only_signer_is(tx_bytes, pubkey):
            raise RuntimeError("Transação exige outros assinantes — recusada por segurança.")

        signed = sign_tx(tx_bytes, kp)

        # Segurança: simular e conferir o gasto (anti-drenagem).
        pre = int(rpc.get_balance(pubkey).get("value", 0))
        sim = simulate(rpc, signed, pubkey)
        val = sim.get("value", {}) or {}
        if val.get("err"):
            raise RuntimeError(f"Simulação falhou: {val.get('err')} | logs: {val.get('logs')}")
        accounts = val.get("accounts") or []
        post = int(accounts[0]["lamports"]) if accounts and accounts[0] else pre
        ok, spent = spend_within_limit(pre, post, sol_amount if action == "buy" else 0.0)
        if not ok:
            raise RuntimeError(
                f"Gasto simulado {spent} lamports acima do permitido — possível drenagem. Recusada."
            )

        result = {"action": action, "mint": mint, "simulated": True, "sent": False,
                  "spent_lamports": spent}
        if not send_it:
            log.info("Simulação OK (%s %s): gastaria ~%d lamports. Não enviado.", action, mint, spent)
            return result

        # Envio real (sem preflight) + confirmação na blockchain.
        from .execute import confirm
        try:
            signature = send(rpc, signed)
            confirm(rpc, signature, timeout=45)
        except TimeoutError as exc:
            # Não confirmou (provável blockhash expirado): refaz e tenta de novo.
            if attempt < attempts - 1:
                last_err = exc
                log.warning("Não confirmou a tempo; refazendo a transação (tentativa %d/%d)...",
                            attempt + 2, attempts)
                continue
            raise RuntimeError(f"Enviado mas não confirmou após {attempts} tentativas: {exc}")
        result.update(sent=True, confirmed=True, signature=str(signature))
        log.warning("%s CONFIRMADO! Assinatura: %s", action.upper(), signature)
        return result

    raise last_err or RuntimeError("Falha ao enviar após várias tentativas.")
