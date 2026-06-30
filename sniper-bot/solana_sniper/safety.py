"""Checagem de segurança de token SPL (heurística anti-honeypot).

Lê a conta do *mint* via RPC e avalia sinais clássicos de risco:
- mint authority ativa  -> o criador pode imprimir supply (diluir você);
- freeze authority ativa -> podem CONGELAR seus tokens (você compra e não vende:
  é exatamente o sintoma "compra e não vende" de honeypot).

Não é garantia absoluta (sniping on-chain é gato e rato), mas filtra os
golpes mais comuns antes de arriscar.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TokenSafety:
    ok: bool
    reasons: list[str]
    mint_authority: str | None
    freeze_authority: str | None
    decimals: int | None
    supply: str | None


def _parse_mint_info(account_result: dict) -> dict:
    value = (account_result or {}).get("value")
    if not value:
        raise ValueError("mint não encontrado (conta inexistente).")
    parsed = value.get("data", {}).get("parsed", {})
    if parsed.get("type") != "mint":
        raise ValueError("a conta informada não é um mint SPL.")
    return parsed.get("info", {})


def check_token_safety(rpc, mint: str) -> TokenSafety:
    """Avalia o mint e retorna o veredito de segurança."""
    info = _parse_mint_info(rpc.get_account_info(mint))
    mint_authority = info.get("mintAuthority")
    freeze_authority = info.get("freezeAuthority")

    reasons: list[str] = []
    if mint_authority:
        reasons.append("mint authority ATIVA — criador pode inflar o supply.")
    if freeze_authority:
        reasons.append("freeze authority ATIVA — podem congelar seus tokens (honeypot).")

    return TokenSafety(
        ok=not reasons,
        reasons=reasons,
        mint_authority=mint_authority,
        freeze_authority=freeze_authority,
        decimals=info.get("decimals"),
        supply=info.get("supply"),
    )
