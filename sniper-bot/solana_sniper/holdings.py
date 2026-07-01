"""Lista os tokens (SPL) que a carteira-isca realmente possui.

Útil para saber o que dá para vender de verdade — o painel mostra "posições
abertas" pelo histórico (CSV), mas isto mostra o SALDO REAL na blockchain.

Uso:
    python -m solana_sniper.holdings
"""

from __future__ import annotations

import logging
import sys

from .config import SolConfig
from .rpc import SolanaRPC
from .wallet import load_burner

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("solana_sniper.holdings")

# pump.fun usa Token-2022; incluímos também o Token program clássico.
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022 = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"


def get_holdings(rpc, owner: str) -> list[tuple[str, float]]:
    """Retorna [(mint, quantidade)] dos tokens com saldo > 0."""
    out: list[tuple[str, float]] = []
    for program in (TOKEN_PROGRAM, TOKEN_2022):
        res = rpc.call("getTokenAccountsByOwner",
                       [owner, {"programId": program}, {"encoding": "jsonParsed"}])
        for acc in res.get("value", []):
            info = acc["account"]["data"]["parsed"]["info"]
            amount = info.get("tokenAmount", {})
            ui = float(amount.get("uiAmount") or 0)
            if ui > 0:
                out.append((info["mint"], ui))
    return out


def run() -> int:
    from .execute import keypair_from_secret
    cfg = SolConfig.load()
    rpc = SolanaRPC(cfg.rpc_url)
    wallet = load_burner(cfg.keypair_path)
    owner = str(keypair_from_secret(wallet.secret).pubkey())

    log.warning("Carteira-isca: %s", owner)
    holdings = get_holdings(rpc, owner)
    if not holdings:
        log.warning("Nenhum token com saldo. (As 'posições abertas' do painel já"
                    " foram vendidas ou viraram pó — nada a vender.)")
        return 0
    log.warning("Tokens com saldo (dá para vender estes):")
    for mint, qty in holdings:
        log.warning("  %s  ->  %s", mint, qty)
    return 0


def main() -> int:
    try:
        return run()
    except (ValueError, PermissionError, FileNotFoundError, RuntimeError) as exc:
        log.error("%s", exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
