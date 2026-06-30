"""Camada 2 anti-rug: auto-saída depois de comprar.

A posição é avaliada periodicamente pelo valor de venda (em SOL) obtido via
cotação Jupiter. `decide_exit` é pura e testável; `manage_position` é a parte
assíncrona que cota, decide e executa a venda.

Regras de saída (a primeira que disparar vence):
  - liquidity_drop : queda brusca do valor entre duas checagens -> rug em curso
  - trailing       : recuo de X% a partir do pico
  - take_profit    : alvo de lucro atingido
  - stop_loss      : perda máxima atingida
  - time_stop      : tempo máximo de exposição estourado
"""

from __future__ import annotations

import logging

from .config import WSOL_MINT
from .execute import execute_swap, get_quote

log = logging.getLogger("solana_sniper.monitor")


def decide_exit(entry: float, peak: float, prev: float, cur: float,
                elapsed: float, cfg) -> tuple[bool, str | None]:
    """Decide se a posição deve ser encerrada. Valores em lamports de SOL."""
    if entry <= 0:
        return False, None
    # Queda brusca entre checagens = liquidez sendo puxada -> sair JÁ.
    if prev > 0 and cfg.liq_drop_pct > 0 and cur <= prev * (1 - cfg.liq_drop_pct):
        return True, "liquidity_drop"
    if cfg.use_trailing and peak > 0 and cur <= peak * (1 - cfg.trailing_pct):
        return True, "trailing"
    if cur >= entry * (1 + cfg.take_profit_pct):
        return True, "take_profit"
    if cur <= entry * (1 - cfg.stop_loss_pct):
        return True, "stop_loss"
    if cfg.time_stop_sec > 0 and elapsed >= cfg.time_stop_sec:
        return True, "time_stop"
    return False, None


def current_sol_value(mint: str, tokens: int, slippage_bps: int) -> int:
    """Quanto SOL (lamports) a posição valeria se vendida agora."""
    try:
        q = get_quote(mint, WSOL_MINT, tokens, slippage_bps)
        return int(q.get("outAmount") or 0)
    except Exception as exc:  # noqa: BLE001  (sem rota = liquidez sumiu)
        log.warning("Sem cotação de venda para %s: %s", mint, exc)
        return 0


async def manage_position(rpc, wallet, cfg, mint: str, tokens: int,
                          entry_lamports: int, clock, sleep) -> dict:
    """Acompanha a posição e vende quando uma regra dispara.

    `clock` retorna o tempo atual (segundos) e `sleep` é a função de espera
    assíncrona — injetados para tornar a função testável.
    """
    start = clock()
    peak = entry_lamports
    prev = entry_lamports

    while True:
        cur = current_sol_value(mint, tokens, cfg.slippage_bps)
        peak = max(peak, cur)
        elapsed = clock() - start
        exit_now, reason = decide_exit(entry_lamports, peak, prev, cur, elapsed, cfg)
        if exit_now:
            log.warning("SAÍDA (%s) %s | valor=%d/%d lamports", reason, mint, cur, entry_lamports)
            try:
                result = execute_swap(rpc, wallet, cfg, mint, WSOL_MINT, tokens)
                sig = result.get("signature")
            except Exception as exc:  # noqa: BLE001
                log.error("Falha ao VENDER %s: %s — tentando de novo no próximo ciclo.", mint, exc)
                prev = cur
                await sleep(cfg.monitor_interval_sec)
                continue
            return {"reason": reason, "exit_lamports": cur, "entry_lamports": entry_lamports,
                    "pnl_lamports": cur - entry_lamports, "signature": sig}
        prev = cur
        await sleep(cfg.monitor_interval_sec)
