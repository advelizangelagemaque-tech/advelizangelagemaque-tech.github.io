"""Auto-snipe pump.fun (via PumpPortal-local) com alerta no Telegram.

Fluxo: detecta token novo -> tenta comprar (a simulação anti-drenagem é a trava)
-> monitora e vende sozinho (trailing/stop/take-profit/time-stop) -> avisa no
Telegram cada compra e venda.

Segurança: modo OBSERVAÇÃO por padrão (não compra). Só compra de verdade com
--live, e mesmo assim com teto por trade (MAX_SPEND_SOL), máximo de trades e
cooldown. Comece SEMPRE sem --live.

Uso:
    python -m solana_sniper.pumpsnipe                       # observação (não compra)
    python -m solana_sniper.pumpsnipe --live --sol 0.01 --max-trades 3
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import os
import sys
from datetime import datetime, timezone

from .config import SolConfig
from .listener import PoolListener, ws_url_from_rpc
from .monitor import decide_exit
from .pumpfun import estimate_sell_value_sol, trade
from .rpc import SolanaRPC
from .safety import check_token_safety
from .wallet import guard_network, load_burner

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("solana_sniper.pumpsnipe")


SOL_JOURNAL = "sol_trades.csv"
_SOL_FIELDS = ["timestamp", "event", "mint", "sol", "pnl_sol", "reason", "signature"]

# Estado das posições abertas, para vender tudo no encerramento (Ctrl+C / stop).
_LIVE: dict = {}


def _record(event: str, mint: str, sol: str = "", pnl_sol: str = "",
            reason: str = "", signature: str = "") -> None:
    """Registra uma operação da Solana no CSV (para aparecer no painel)."""
    new = not os.path.exists(SOL_JOURNAL)
    with open(SOL_JOURNAL, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_SOL_FIELDS)
        if new:
            w.writeheader()
        w.writerow({
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "event": event, "mint": mint, "sol": sol, "pnl_sol": pnl_sol,
            "reason": reason, "signature": signature,
        })


def _notifier():
    from sniper.notify import Notifier
    return Notifier(os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
                    os.getenv("TELEGRAM_CHAT_ID", "").strip())


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Auto-snipe pump.fun com Telegram")
    p.add_argument("--sol", type=float, default=0.01, help="SOL por compra.")
    p.add_argument("--live", action="store_true", help="Compra de verdade (sem isto, só observa/avisa).")
    p.add_argument("--max-trades", type=int, default=3, help="Para após N compras (0 = sem limite).")
    p.add_argument("--cooldown", type=int, default=30, help="Segundos entre compras.")
    return p.parse_args()


def _freeze_ok(rpc, mint: str) -> bool:
    """Trava barata que se aplica a pump.fun: recusa se houver freeze authority."""
    try:
        s = check_token_safety(rpc, mint)
        return s.freeze_authority is None
    except Exception:  # noqa: BLE001  (token novo demais para checar — não bloqueia)
        return True


async def _watch_and_exit(rpc, wallet, cfg, mint, notifier, loop):
    """Acompanha a posição e vende quando uma regra de saída dispara."""
    entry = None
    for _ in range(5):
        v = estimate_sell_value_sol(rpc, wallet, cfg, mint)
        if v and v > 0:
            entry = v
            break
        await asyncio.sleep(2)
    if not entry:
        log.warning("Não consegui avaliar %s para monitorar; vendendo por segurança.", mint)
        try:
            trade(rpc, wallet, cfg, "sell", mint, "100%", send_it=True)
        except Exception as exc:  # noqa: BLE001
            log.error("Falha ao vender %s: %s", mint, exc)
        _LIVE.get("open", set()).discard(mint)
        return

    start = loop.time()
    peak = prev = entry
    while True:
        cur = estimate_sell_value_sol(rpc, wallet, cfg, mint)
        if cur is None:
            await asyncio.sleep(cfg.monitor_interval_sec)
            continue
        peak = max(peak, cur)
        exit_now, reason = decide_exit(entry, peak, prev, cur, loop.time() - start, cfg)
        if exit_now:
            pnl = (cur - entry) / 1e9
            log.warning("SAÍDA (%s) %s | PnL~%.4f SOL", reason, mint, pnl)
            try:
                res = trade(rpc, wallet, cfg, "sell", mint, "100%", send_it=True)
                _record("SELL", mint, pnl_sol=f"{pnl:.6f}", reason=reason,
                        signature=str(res.get("signature") or ""))
                notifier.send(f"🔴 VENDI {mint}\nmotivo: {reason} | PnL~{pnl:+.4f} SOL\n"
                              f"https://solscan.io/tx/{res.get('signature')}")
            except Exception as exc:  # noqa: BLE001
                log.error("Falha ao vender %s: %s", mint, exc)
            _LIVE.get("open", set()).discard(mint)
            return
        prev = cur
        await asyncio.sleep(cfg.monitor_interval_sec)


async def _amain(args) -> int:
    cfg = SolConfig.load()
    if args.live:
        guard_network(cfg.network, cfg.allow_mainnet)
    rpc = SolanaRPC(cfg.rpc_url)
    wallet = load_burner(cfg.keypair_path) if args.live else None
    notifier = _notifier()
    loop = asyncio.get_event_loop()

    # Registra o estado para o encerramento seguro vender as posições abertas.
    if args.live:
        _LIVE.update(cfg=cfg, rpc=rpc, wallet=wallet, open=set())

    modo = f"LIVE (compra {args.sol} SOL)" if args.live else "OBSERVAÇÃO (não compra)"
    log.warning("pump.fun auto-snipe | %s | max-trades=%s | teto=%s SOL",
                modo, args.max_trades, cfg.max_spend_sol)
    notifier.send(f"🚀 Auto-snipe pump.fun iniciado | {modo}")

    seen: set[str] = set()
    state = {"trades": 0, "last_buy": 0.0}
    stop = asyncio.Event()

    async def on_mint(mint: str, sig: str) -> None:
        if mint in seen or (args.max_trades and state["trades"] >= args.max_trades):
            return
        seen.add(mint)

        if not _freeze_ok(rpc, mint):
            log.warning("PULANDO %s — freeze authority ativa (honeypot).", mint)
            return
        if args.cooldown and (loop.time() - state["last_buy"]) < args.cooldown:
            return  # cooldown entre compras

        if not args.live:
            notifier.send(f"👀 Candidato detectado: {mint}\n(modo observação — não comprei)")
            log.info("[observação] compraria %s", mint)
            return

        try:
            res = trade(rpc, wallet, cfg, "buy", mint, args.sol, send_it=True)
        except Exception as exc:  # noqa: BLE001
            log.warning("PULANDO %s — não passou nas travas/compra: %s", mint, exc)
            return

        state["trades"] += 1
        state["last_buy"] = loop.time()
        _LIVE["open"].add(mint)   # marca como posição aberta
        log.warning("COMPROU %s | assinatura %s", mint, res.get("signature"))
        _record("BUY", mint, sol=f"{args.sol}", signature=str(res.get("signature") or ""))
        notifier.send(f"🟢 COMPREI {mint}\n{args.sol} SOL\n"
                      f"https://solscan.io/tx/{res.get('signature')}")

        asyncio.create_task(_watch_and_exit(rpc, wallet, cfg, mint, notifier, loop))

        if args.max_trades and state["trades"] >= args.max_trades:
            log.warning("MAX_TRADES (%d) atingido — não compra mais (posições seguem monitoradas).",
                        args.max_trades)

    listener = PoolListener(rpc, cfg.ws_url or ws_url_from_rpc(cfg.rpc_url), program="pump")
    runner = asyncio.create_task(listener.run(on_mint))
    await asyncio.wait({runner, asyncio.create_task(stop.wait())},
                       return_when=asyncio.FIRST_COMPLETED)
    runner.cancel()
    return 0


def _liquidate_open() -> None:
    """Vende todas as posições abertas ao encerrar (para não abandonar tokens)."""
    open_mints = _LIVE.get("open") or set()
    if not open_mints:
        return
    cfg, rpc, wallet = _LIVE.get("cfg"), _LIVE.get("rpc"), _LIVE.get("wallet")
    log.warning("Encerrando: vendendo %d posição(ões) aberta(s)...", len(open_mints))
    for mint in list(open_mints):
        try:
            res = trade(rpc, wallet, cfg, "sell", mint, "100%", send_it=True)
            _record("SELL", mint, reason="encerramento", signature=str(res.get("signature") or ""))
            log.warning("Vendido na saída: %s", mint)
        except Exception as exc:  # noqa: BLE001
            log.error("NÃO consegui vender %s no encerramento: %s "
                      "— venda manual pelo painel!", mint, exc)
        open_mints.discard(mint)


def _raise_kbd(*_a):
    raise KeyboardInterrupt


def main() -> int:
    args = parse_args()
    # systemctl stop envia SIGTERM: tratamos como Ctrl+C para vender antes de sair.
    import signal
    try:
        signal.signal(signal.SIGTERM, _raise_kbd)
    except (ValueError, OSError):  # pragma: no cover  (fora da thread principal)
        pass
    try:
        return asyncio.run(_amain(args))
    except KeyboardInterrupt:
        log.warning("Interrompido — vendendo posições abertas antes de sair...")
        _liquidate_open()
        log.info("Tchau!")
        return 0
    except (ValueError, PermissionError, FileNotFoundError) as exc:
        log.error("%s", exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
