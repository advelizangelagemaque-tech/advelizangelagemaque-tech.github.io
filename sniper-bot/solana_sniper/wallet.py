"""Carteira-isca (burner) com travas de segurança.

Carrega o keypair de um arquivo JSON (formato padrão da Solana CLI: lista de
inteiros). NÃO assina transações aqui — assinatura exige a lib `solders` e só
deve ser ligada após validação em devnet (ver README).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass


@dataclass
class BurnerWallet:
    secret: bytes
    keypair_path: str

    @property
    def loaded(self) -> bool:
        return len(self.secret) in (32, 64)


def guard_network(network: str, allow_mainnet: bool) -> None:
    """Bloqueia mainnet a menos que liberado de propósito."""
    if network == "mainnet" and not allow_mainnet:
        raise PermissionError(
            "NETWORK=mainnet bloqueado. Valide em devnet primeiro e, com "
            "consciência do risco, defina ALLOW_MAINNET=true."
        )
    if network not in ("devnet", "mainnet"):
        raise ValueError(f"NETWORK inválida: {network!r} (use devnet ou mainnet).")


def load_burner(keypair_path: str) -> BurnerWallet:
    """Carrega a carteira-isca de um arquivo JSON (lista de bytes)."""
    path = os.path.expanduser(keypair_path)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Keypair não encontrado em {path}. Crie uma carteira-isca "
            "(ex.: `solana-keygen new -o burner.json`) e proteja com chmod 600."
        )
    # Aviso de permissão: a chave nunca deve ficar legível por outros.
    mode = oct(os.stat(path).st_mode)[-3:]
    if mode not in ("600", "400"):
        raise PermissionError(
            f"Permissão do keypair muito aberta ({mode}). Rode: chmod 600 {path}"
        )
    with open(path, encoding="utf-8") as f:
        arr = json.load(f)
    if not isinstance(arr, list) or not all(isinstance(x, int) for x in arr):
        raise ValueError("Formato de keypair inválido (esperado lista de inteiros).")
    return BurnerWallet(secret=bytes(arr), keypair_path=path)
