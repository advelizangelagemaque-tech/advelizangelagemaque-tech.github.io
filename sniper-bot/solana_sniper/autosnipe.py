"""Auto-snipe na Solana: detecta tokens novos e compra automaticamente.

Uso:
    # SEMPRE comece simulando (detecta e checa segurança, não compra):
    python -m solana_sniper.autosnipe --dry-run

    # Compra de verdade (devnet por padrão), no máximo 1 token:
    python -m solana_sniper.autosnipe --amount-sol 0.01 --max-trades 1
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from .config import LAMPORTS_PER_SOL, WSOL_MINT, SolConfig
from .execute import execute_swap
from .listener import PoolListener, ws_url_from_rpc
from .monitor import manage_position
from .rpc import SolanaRPC
from .rugcheck import assess_pre_buy
from .safety import check_token_safety
from .wallet import guard_network, load_burner

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("solana_sniper.autosnipe")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Auto-snipe Solana (experimental)")
    p.add_argument("--amount-sol", type=float, default=0.01, help="Quanto de SOL por compra.")
    p.add_argument("--dry-run", action="store_true", help="Detecta e checa, mas não compra.")
    p.add_argument("--program", choices=["pump", "raydium"], default="pump",
                   help="Fonte de novos tokens (default: pump.fun).")
    p.add_argument("--max-trades", type=int, default=1, help="Para após N compras (0 = sem limite).")
    return p.parse_args()


async def _amain(args) -> int:
    cfg = SolConfig.load()
    # Em --dry-run nada é comprado (só observa/checa), então a mainnet é liberada
    # para leitura. Fora do dry-run, a trava de mainnet continua valendo.
    if not args.dry_run:
        guard_network(cfg.network, cfg.allow_mainnet)
    rpc = SolanaRPC(cfg.rpc_url)
    wallet = None if args.dry_run else load_burner(cfg.keypair_path)
    amount_lamports = int(args.amount_sol * LAMPORTS_PER_SOL)

    log.warning("Auto-snipe | rede=%s | programa=%s | %s | teto=%s SOL",
                cfg.network, args.program,
                "DRY-RUN" if args.dry_run else f"compra {args.amount_sol} SOL",
                cfg.max_spend_sol)

    seen: set[str] = set()
    state = {"trades": 0}
    stop = asyncio.Event()
    loop = asyncio.get_event_loop()
    positions: list[asyncio.Task] = []

    async def on_mint(mint: str, sig: str) -> None:
        if mint in seen:
            return
        if args.max_trades and state["trades"] >= args.max_trades:
            return  # já atingiu o limite de compras; aguardando posições fecharem
        seen.add(mint)

        # Camada authority (mint/freeze). Tokens recém-nascidos podem ainda
        # não estar consultáveis — nesse caso, pulamos de forma limpa.
        try:
            safety = check_token_safety(rpc, mint)
        except Exception as exc:  # noqa: BLE001
            log.info("PULANDO %s — ainda não verificável (%s).", mint, exc)
            return
        if not safety.ok:
            for r in safety.reasons:
                log.warning("PULANDO %s — %s", mint, r)
            return

        # Camada 1: simulação de venda + holders (anti-honeypot/rug pré-compra).
        verdict = assess_pre_buy(rpc, mint, cfg, amount_lamports)
        if not verdict.ok:
            for r in verdict.reasons:
                log.warning("PULANDO %s — %s", mint, r)
            return
        rt = verdict.metrics.get("roundtrip", {})
        log.info("Anti-rug OK: %s | vendável, perda ida-e-volta %.0f%%",
                 mint, rt.get("loss_pct", 0) * 100)

        if args.dry_run:
            log.info("[dry-run] compraria %s com %s SOL (passou nas checagens).",
                     mint, args.amount_sol)
            return

        try:
            result = execute_swap(rpc, wallet, cfg, WSOL_MINT, mint, amount_lamports)
            tokens = int((result.get("quote") or {}).get("outAmount") or 0)
            log.warning("COMPROU %s | %d tokens | assinatura %s", mint, tokens, result["signature"])
            state["trades"] += 1
        except Exception as exc:  # noqa: BLE001
            log.error("Falha ao comprar %s: %s", mint, exc)
            return

        # Camada 2: monitora e vende sozinho (trailing/stop/time/liquidez).
        async def _watch():
            res = await manage_position(rpc, wallet, cfg, mint, tokens, amount_lamports,
                                        clock=loop.time, sleep=asyncio.sleep)
            log.warning("POSIÇÃO ENCERRADA %s | motivo=%s | PnL=%d lamports",
                        mint, res["reason"], res["pnl_lamports"])
            if args.max_trades and state["trades"] >= args.max_trades:
                stop.set()
        positions.append(asyncio.create_task(_watch()))

    # WS pode ser separado do RPC: stream pelo público (grátis) e REST pela Helius.
    ws_url = cfg.ws_url or ws_url_from_rpc(cfg.rpc_url)
    log.warning("Stream de logs: %s", ws_url.split("?")[0])
    listener = PoolListener(rpc, ws_url, program=args.program)
    runner = asyncio.create_task(listener.run(on_mint))
    stopper = asyncio.create_task(stop.wait())
    await asyncio.wait({runner, stopper}, return_when=asyncio.FIRST_COMPLETED)
    runner.cancel()
    return 0


def main() -> int:
    args = parse_args()
    try:
        return asyncio.run(_amain(args))
    except KeyboardInterrupt:
        log.info("Interrompido. Tchau!")
        return 0
    except (ValueError, PermissionError, FileNotFoundError) as exc:
        log.error("%s", exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
