"""Execução de swap na Solana via Jupiter v6 + assinatura com solders.

Fluxo:
  1. get_quote        -> melhor rota de preço (read-only)
  2. get_swap_tx      -> Jupiter monta a transação (base64)
  3. sign_transaction -> assina com a carteira-isca (solders)
  4. send_signed      -> envia para a rede
  5. confirm          -> aguarda confirmação

Travas de segurança ficam em execute_swap (rede, teto de gasto, dry-run).
A assinatura usa `solders` (import tardio) — instale via requirements-solana.txt.
"""

from __future__ import annotations

import base64
import json
import time
import urllib.parse
import urllib.request

JUPITER_QUOTE = "https://quote-api.jup.ag/v6/quote"
JUPITER_SWAP = "https://quote-api.jup.ag/v6/swap"


# ---- Jupiter (read-only / montagem) ----------------------------------------

def get_quote(input_mint: str, output_mint: str, amount: int,
              slippage_bps: int = 100, timeout: int = 10) -> dict:
    """Cotação de swap. `amount` em unidades mínimas do input_mint (lamports p/ SOL)."""
    qs = urllib.parse.urlencode({
        "inputMint": input_mint, "outputMint": output_mint,
        "amount": amount, "slippageBps": slippage_bps,
    })
    with urllib.request.urlopen(f"{JUPITER_QUOTE}?{qs}", timeout=timeout) as resp:
        return json.loads(resp.read())


def get_swap_tx(quote: dict, user_pubkey: str, timeout: int = 10) -> str:
    """Pede ao Jupiter a transação de swap (base64) para a rota cotada."""
    payload = json.dumps({
        "quoteResponse": quote,
        "userPublicKey": user_pubkey,
        "wrapAndUnwrapSol": True,
        "dynamicComputeUnitLimit": True,
    }).encode()
    req = urllib.request.Request(
        JUPITER_SWAP, data=payload, headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())["swapTransaction"]


# ---- Assinatura e envio (solders) ------------------------------------------

def keypair_from_secret(secret: bytes):
    """Constrói o Keypair (solders) a partir dos bytes da carteira-isca."""
    from solders.keypair import Keypair
    if len(secret) == 64:
        return Keypair.from_bytes(secret)
    if len(secret) == 32:
        return Keypair.from_seed(secret)
    raise ValueError("Secret deve ter 32 (seed) ou 64 bytes.")


def sign_transaction(swap_tx_b64: str, keypair) -> str:
    """Assina a transação versionada do Jupiter e devolve em base64."""
    from solders.transaction import VersionedTransaction
    from solders.message import to_bytes_versioned
    raw = base64.b64decode(swap_tx_b64)
    tx = VersionedTransaction.from_bytes(raw)
    signature = keypair.sign_message(to_bytes_versioned(tx.message))
    signed = VersionedTransaction.populate(tx.message, [signature])
    return base64.b64encode(bytes(signed)).decode()


def send_signed(rpc, signed_tx_b64: str) -> str:
    """Envia a transação assinada; retorna a assinatura (txid)."""
    return rpc.call("sendTransaction", [
        signed_tx_b64,
        {"encoding": "base64", "skipPreflight": False, "maxRetries": 3},
    ])


def confirm(rpc, signature: str, timeout: int = 60, interval: float = 2.0) -> dict:
    """Aguarda a confirmação da transação (polling em getSignatureStatuses)."""
    waited = 0.0
    while waited < timeout:
        res = rpc.call("getSignatureStatuses", [[signature], {"searchTransactionHistory": True}])
        status = (res.get("value") or [None])[0]
        if status:
            if status.get("err"):
                raise RuntimeError(f"Transação falhou on-chain: {status['err']}")
            conf = status.get("confirmationStatus")
            if conf in ("confirmed", "finalized"):
                return status
        time.sleep(interval)
        waited += interval
    raise TimeoutError(f"Sem confirmação em {timeout}s para {signature}.")


# ---- Orquestração com travas de segurança ----------------------------------

def execute_swap(rpc, wallet, cfg, input_mint: str, output_mint: str,
                 amount_lamports: int, dry_run: bool = False) -> dict:
    """Compra `output_mint` gastando `amount_lamports` de `input_mint`.

    Travas: rede (devnet/mainnet), teto de gasto e dry-run.
    """
    from .wallet import guard_network
    guard_network(cfg.network, cfg.allow_mainnet)

    from .config import LAMPORTS_PER_SOL, WSOL_MINT
    if input_mint == WSOL_MINT:
        max_lamports = int(cfg.max_spend_sol * LAMPORTS_PER_SOL)
        if amount_lamports > max_lamports:
            raise ValueError(
                f"Gasto {amount_lamports} lamports excede o teto "
                f"MAX_SPEND_SOL={cfg.max_spend_sol} ({max_lamports} lamports)."
            )

    quote = get_quote(input_mint, output_mint, amount_lamports, cfg.slippage_bps)
    if dry_run:
        return {"sent": False, "dry_run": True, "quote": quote}

    keypair = keypair_from_secret(wallet.secret)
    swap_tx = get_swap_tx(quote, str(keypair.pubkey()))
    signed = sign_transaction(swap_tx, keypair)
    signature = send_signed(rpc, signed)
    status = confirm(rpc, signature)
    return {"sent": True, "signature": str(signature), "status": status, "quote": quote}
