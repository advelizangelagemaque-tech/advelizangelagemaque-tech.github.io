"""Compra manual de um token pump.fun (via PumpPortal-local), simulação-primeiro.

Uso:
    # SIMULA (não gasta nada) — comece SEMPRE por aqui:
    python -m solana_sniper.pumpbuy --mint <ENDERECO_DO_TOKEN> --sol 0.01

    # COMPRA de verdade (precisa NETWORK=mainnet e ALLOW_MAINNET=true no .env):
    python -m solana_sniper.pumpbuy --mint <ENDERECO_DO_TOKEN> --sol 0.01 --send

    # VENDER 100% do token de volta:
    python -m solana_sniper.pumpbuy --mint <ENDERECO_DO_TOKEN> --sell --send
"""

from __future__ import annotations

import argparse
import logging
import sys

from .config import SolConfig
from .pumpfun import trade
from .rpc import SolanaRPC
from .wallet import load_burner

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("solana_sniper.pumpbuy")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Compra/venda manual no pump.fun")
    p.add_argument("--mint", required=True, help="Endereço (mint) do token.")
    p.add_argument("--sol", type=float, default=0.01, help="Quanto de SOL gastar (na compra).")
    p.add_argument("--sell", action="store_true", help="Vender 100%% do token em vez de comprar.")
    p.add_argument("--send", action="store_true", help="Envia de verdade (sem isto, só simula).")
    return p.parse_args()


def run(args) -> int:
    cfg = SolConfig.load()
    rpc = SolanaRPC(cfg.rpc_url)
    wallet = load_burner(cfg.keypair_path)

    action = "sell" if args.sell else "buy"
    amount = 100.0 if args.sell else args.sol   # venda: 100% dos tokens
    modo = "ENVIO REAL" if args.send else "SIMULAÇÃO (não gasta)"
    log.warning("pump.fun %s | mint=%s | %s | %s",
                action, args.mint, f"{args.sol} SOL" if action == "buy" else "100%", modo)

    result = trade(rpc, wallet, cfg, action, args.mint, amount, send_it=args.send)

    if not result["sent"]:
        log.info("✅ Simulação OK — gastaria ~%.6f SOL. Rode com --send para valer.",
                 result["spent_lamports"] / 1e9)
    else:
        log.warning("✅ %s ENVIADO! Assinatura: %s", action.upper(), result["signature"])
        log.warning("Acompanhe em: https://solscan.io/tx/%s", result["signature"])
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
