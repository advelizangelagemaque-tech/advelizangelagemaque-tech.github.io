"""Saque de SOL da carteira-isca para outro endereço (ex.: sua Bybit).

Uso:
    # ver o saldo:
    python -m solana_sniper.withdraw --saldo

    # sacar 0.05 SOL para um endereço:
    python -m solana_sniper.withdraw --to <ENDERECO_SOL_BYBIT> --sol 0.05

    # sacar TUDO (deixando uma folga p/ taxa/rent):
    python -m solana_sniper.withdraw --to <ENDERECO_SOL_BYBIT> --tudo

IMPORTANTE: use o endereço de depósito de SOL da Bybit na REDE SOLANA.
"""

from __future__ import annotations

import argparse
import base64
import logging
import sys

from .config import LAMPORTS_PER_SOL, SolConfig
from .rpc import SolanaRPC
from .wallet import guard_network, load_burner

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("solana_sniper.withdraw")

# Folga deixada na carteira: taxa da tx + isenção de aluguel (rent), ~0.002 SOL.
BUFFER_LAMPORTS = 2_000_000


def amount_to_send(balance: int, sol: float | None, tudo: bool,
                   buffer: int = BUFFER_LAMPORTS) -> int:
    """Calcula quantos lamports enviar, sempre deixando a folga na carteira."""
    if tudo:
        return balance - buffer
    if sol is None:
        raise ValueError("Informe --sol <valor> ou use --tudo.")
    return int(sol * LAMPORTS_PER_SOL)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Saque de SOL da carteira-isca")
    p.add_argument("--to", help="Endereço de destino (depósito SOL da Bybit).")
    p.add_argument("--sol", type=float, help="Quanto de SOL sacar.")
    p.add_argument("--tudo", action="store_true", help="Saca tudo (menos a folga).")
    p.add_argument("--saldo", action="store_true", help="Só mostra o saldo e sai.")
    return p.parse_args()


def run(args) -> int:
    from solders.hash import Hash
    from solders.message import MessageV0
    from solders.pubkey import Pubkey
    from solders.system_program import TransferParams, transfer
    from solders.transaction import VersionedTransaction

    from .execute import confirm, keypair_from_secret

    cfg = SolConfig.load()
    rpc = SolanaRPC(cfg.rpc_url)
    wallet = load_burner(cfg.keypair_path)
    kp = keypair_from_secret(wallet.secret)
    pubkey = str(kp.pubkey())

    balance = int(rpc.get_balance(pubkey).get("value", 0))
    log.warning("Carteira-isca: %s", pubkey)
    log.warning("Saldo atual: %.6f SOL", balance / LAMPORTS_PER_SOL)
    if args.saldo:
        return 0

    if not args.to:
        log.error("Informe o destino com --to <ENDERECO> (ou use --saldo para só ver o saldo).")
        return 2

    dest = Pubkey.from_string(args.to)   # valida o endereço
    lamports = amount_to_send(balance, args.sol, args.tudo)
    if lamports <= 0:
        log.error("Valor a sacar inválido (%d lamports).", lamports)
        return 2
    if lamports > balance - BUFFER_LAMPORTS:
        log.error("Saldo insuficiente: pediu %.6f SOL, disponível ~%.6f SOL (deixando folga).",
                  lamports / LAMPORTS_PER_SOL, (balance - BUFFER_LAMPORTS) / LAMPORTS_PER_SOL)
        return 2

    guard_network(cfg.network, cfg.allow_mainnet)  # saque real exige mainnet liberada

    ix = transfer(TransferParams(from_pubkey=kp.pubkey(), to_pubkey=dest, lamports=lamports))
    blockhash = Hash.from_string(rpc.get_latest_blockhash()["value"]["blockhash"])
    msg = MessageV0.try_compile(kp.pubkey(), [ix], [], blockhash)
    tx = VersionedTransaction(msg, [kp])

    b64 = base64.b64encode(bytes(tx)).decode()
    log.warning("Sacando %.6f SOL para %s ...", lamports / LAMPORTS_PER_SOL, dest)
    # skipPreflight: o blockhash acabou de ser buscado; pular o preflight evita o
    # 'BlockhashNotFound' quando o nó da Helius ainda não o viu.
    signature = rpc.call("sendTransaction", [b64, {
        "encoding": "base64", "skipPreflight": True, "maxRetries": 3,
    }])
    confirm(rpc, signature)
    log.warning("✅ SAQUE CONFIRMADO! https://solscan.io/tx/%s", signature)
    log.warning("Pode levar alguns minutos para aparecer na Bybit.")
    return 0


def main() -> int:
    args = parse_args()
    try:
        return run(args)
    except (ValueError, PermissionError, FileNotFoundError, RuntimeError) as exc:
        log.error("%s", exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
