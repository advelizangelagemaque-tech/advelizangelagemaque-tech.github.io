"""Configuração do módulo Solana (lida do .env)."""

from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # pragma: no cover
    pass

# Endereço do Wrapped SOL (usado como moeda de entrada para comprar tokens).
WSOL_MINT = "So11111111111111111111111111111111111111112"
LAMPORTS_PER_SOL = 1_000_000_000


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "sim"}


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw not in (None, "") else default


@dataclass
class SolConfig:
    network: str
    allow_mainnet: bool
    rpc_url: str
    keypair_path: str
    max_spend_sol: float
    slippage_bps: int

    @classmethod
    def load(cls) -> "SolConfig":
        from .rpc import PUBLIC_RPC
        network = os.getenv("NETWORK", "devnet").strip().lower()
        rpc_url = os.getenv("SOLANA_RPC_URL", "").strip() or PUBLIC_RPC.get(network, "")
        cfg = cls(
            network=network,
            allow_mainnet=_get_bool("ALLOW_MAINNET", False),
            rpc_url=rpc_url,
            keypair_path=os.getenv("BURNER_KEYPAIR_PATH", "~/.config/solana/burner.json"),
            max_spend_sol=_get_float("MAX_SPEND_SOL", 0.05),
            slippage_bps=int(_get_float("SLIPPAGE_BPS", 100)),
        )
        cfg.validate()
        return cfg

    def validate(self) -> None:
        errors = []
        if self.network not in ("devnet", "mainnet"):
            errors.append("NETWORK deve ser devnet ou mainnet.")
        if not self.rpc_url:
            errors.append("SOLANA_RPC_URL vazio e sem RPC público para a rede.")
        if self.max_spend_sol <= 0:
            errors.append("MAX_SPEND_SOL deve ser > 0.")
        if not (0 < self.slippage_bps <= 5000):
            errors.append("SLIPPAGE_BPS deve estar entre 1 e 5000 (0.01%–50%).")
        if errors:
            raise ValueError("Config Solana inválida:\n- " + "\n- ".join(errors))
