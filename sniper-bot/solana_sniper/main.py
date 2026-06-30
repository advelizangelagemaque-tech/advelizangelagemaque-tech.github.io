"""CLI do sniper Solana: checa segurança do token e compra com SOL.

Uso:
    python -m solana_sniper.main --mint <ENDERECO_DO_TOKEN> --amount-sol 0.01 --dry-run
    python -m solana_sniper.main --mint <ENDERECO_DO_TOKEN> --amount-sol 0.01

Sempre rode com --dry-run primeiro. Mantenha NETWORK=devnet até validar.
"""

from __future__ import annotations

import argparse
import logging
import sys

from .config import LAMPORTS_PER_SOL, WSOL_MINT, SolConfig
from .execute import execute_swap
from .rpc import SolanaRPC
from .safety import check_token_safety
from .wallet import guard_network, load_burner

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("solana_sniper")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Sniper Solana (experimental)")
    p.add_argument("--mint", required=True, help="Endereço (mint) do token a comprar.")
    p.add_argument("--amount-sol", type=float, default=0.01, help="Quanto de SOL gastar.")
    p.add_argument("--dry-run", action="store_true", help="Só cota, não envia transação.")
    p.add_argument("--force", action="store_true",
                   help="Compra mesmo se a checagem de segurança reprovar (PERIGOSO).")
    return p.parse_args()


def run(args) -> int:
    cfg = SolConfig.load()
    guard_network(cfg.network, cfg.allow_mainnet)
    log.warning("Rede=%s | teto=%s SOL | slippage=%dbps", cfg.network, cfg.max_spend_sol,
                cfg.slippage_bps)

    rpc = SolanaRPC(cfg.rpc_url)

    # 1) Checagem de segurança (anti-honeypot).
    safety = check_token_safety(rpc, args.mint)
    if safety.ok:
        log.info("Segurança OK: sem mint/freeze authority ativas.")
    else:
        for r in safety.reasons:
            log.warning("RISCO: %s", r)
        if not args.force:
            log.error("Compra abortada pela checagem de segurança. Use --force para ignorar (perigoso).")
            return 1
        log.warning(">>> --force ativo: comprando MESMO com risco. <<<")

    # 2) Carteira-isca e execução.
    wallet = load_burner(cfg.keypair_path)
    amount_lamports = int(args.amount_sol * LAMPORTS_PER_SOL)

    result = execute_swap(rpc, wallet, cfg, WSOL_MINT, args.mint, amount_lamports,
                          dry_run=args.dry_run)
    if result.get("dry_run"):
        out = result["quote"].get("outAmount")
        log.info("[dry-run] cotação: receberia ~%s unidades do token. Nada enviado.", out)
    else:
        log.warning("Swap enviado! Assinatura: %s", result["signature"])
    return 0


def main() -> int:
    args = parse_args()
    try:
        return run(args)
    except (ValueError, PermissionError, FileNotFoundError) as exc:
        log.error("%s", exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
