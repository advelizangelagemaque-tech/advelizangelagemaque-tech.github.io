"""Leitura da curva de liquidez (bonding curve) de um token pump.fun.

Permite filtrar por tração antes de comprar: quanto SOL já entrou na curva
(compradores reais) e o market cap estimado. Tudo read-only (sem assinar nada).

Layout da conta (Anchor, após 8 bytes de discriminador):
  virtual_token_reserves : u64
  virtual_sol_reserves   : u64
  real_token_reserves    : u64
  real_sol_reserves      : u64   <- SOL "de verdade" já na curva (tração)
  token_total_supply     : u64
  complete               : bool  <- True = já graduou
"""

from __future__ import annotations

import base64
from struct import unpack

PUMP_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
LAMPORTS_PER_SOL = 1_000_000_000


def bonding_curve_pda(mint: str) -> str:
    from solders.pubkey import Pubkey
    pda, _ = Pubkey.find_program_address(
        [b"bonding-curve", bytes(Pubkey.from_string(mint))],
        Pubkey.from_string(PUMP_PROGRAM),
    )
    return str(pda)


def decode_curve(raw: bytes) -> dict | None:
    """Decodifica os bytes da conta da curva. Retorna None se inválido."""
    if len(raw) < 8 + 40 + 1:
        return None
    vtr, vsr, rtr, rsr, tts = unpack("<QQQQQ", raw[8:48])
    complete = raw[48] != 0
    mcap_sol = (vsr * tts / vtr) / LAMPORTS_PER_SOL if vtr else 0.0
    return {
        "virtual_token_reserves": vtr, "virtual_sol_reserves": vsr,
        "real_token_reserves": rtr, "real_sol_reserves": rsr,
        "token_total_supply": tts, "complete": complete,
        "sol_in_curve": rsr / LAMPORTS_PER_SOL,   # tração: SOL real já investido
        "mcap_sol": mcap_sol,                      # market cap estimado (em SOL)
    }


def read_curve(rpc, mint: str) -> dict | None:
    """Lê e decodifica a curva do token. Retorna None se ainda não existe."""
    pda = bonding_curve_pda(mint)
    res = rpc.call("getAccountInfo", [pda, {"encoding": "base64", "commitment": "confirmed"}])
    val = res.get("value")
    if not val:
        return None
    raw = base64.b64decode(val["data"][0])
    return decode_curve(raw)


def curve_gate(c0: dict | None, c1: dict | None, min_sol: float, max_sol: float,
               require_growth: bool) -> tuple[bool, str]:
    """Decide se o token passa no filtro de tração/momentum.

    c0 = leitura inicial; c1 = leitura após a janela (para momentum).
    """
    if c0 is None:
        return False, "curva ainda não encontrada"
    if c0.get("complete"):
        return False, "já graduou"
    s0 = c0["sol_in_curve"]
    if min_sol and s0 < min_sol:
        return False, f"tração baixa ({s0:.2f} SOL na curva < mín {min_sol})"
    if max_sol and s0 > max_sol:
        return False, f"tarde demais ({s0:.2f} SOL na curva > máx {max_sol})"
    if require_growth:
        if c1 is None:
            return False, "sem 2ª leitura para medir momentum"
        if c1["sol_in_curve"] <= s0:
            return False, f"sem momentum (curva não cresceu: {s0:.2f} -> {c1['sol_in_curve']:.2f} SOL)"
    return True, "ok"
