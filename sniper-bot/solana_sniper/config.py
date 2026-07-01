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
    ws_url: str
    keypair_path: str
    max_spend_sol: float
    slippage_bps: int
    priority_fee_sol: float
    # Anti-rug — pré-compra
    max_roundtrip_loss_pct: float   # honeypot se perder mais que isso ida-e-volta
    max_top_holder_pct: float       # recusa se 1 carteira tiver mais que isso (0 = off)
    # Anti-rug — auto-saída (pós-compra), tudo em fração do valor de entrada
    use_trailing: bool
    trailing_pct: float
    take_profit_pct: float
    stop_loss_pct: float
    time_stop_sec: int              # sai depois de N segundos (0 = sem time-stop)
    liq_drop_pct: float             # venda de emergência se o valor cair tanto entre checagens
    monitor_interval_sec: float
    # Filtro de lançamento pump.fun (tração/momentum; 0 = desligado)
    min_sol_in_curve: float         # só compra se já houver este SOL na curva
    max_sol_in_curve: float         # não compra se passou deste SOL (tarde demais)
    buy_delay_sec: float            # espera antes de avaliar (deixa a curva "assentar")
    momentum_window_sec: float      # janela para medir crescimento
    require_growth: bool            # só compra se a curva cresceu na janela

    @classmethod
    def load(cls) -> "SolConfig":
        from .rpc import PUBLIC_RPC
        network = os.getenv("NETWORK", "devnet").strip().lower()
        rpc_url = os.getenv("SOLANA_RPC_URL", "").strip() or PUBLIC_RPC.get(network, "")
        cfg = cls(
            network=network,
            allow_mainnet=_get_bool("ALLOW_MAINNET", False),
            rpc_url=rpc_url,
            ws_url=os.getenv("SOLANA_WS_URL", "").strip(),
            keypair_path=os.getenv("BURNER_KEYPAIR_PATH", "~/.config/solana/burner.json"),
            max_spend_sol=_get_float("MAX_SPEND_SOL", 0.05),
            slippage_bps=int(_get_float("SLIPPAGE_BPS", 100)),
            priority_fee_sol=_get_float("PRIORITY_FEE_SOL", 0.00005),
            max_roundtrip_loss_pct=_get_float("MAX_ROUNDTRIP_LOSS_PCT", 0.20),
            max_top_holder_pct=_get_float("MAX_TOP_HOLDER_PCT", 0.0),
            use_trailing=_get_bool("SOL_USE_TRAILING", True),
            trailing_pct=_get_float("SOL_TRAILING_PCT", 0.20),
            take_profit_pct=_get_float("SOL_TAKE_PROFIT_PCT", 0.50),
            stop_loss_pct=_get_float("SOL_STOP_LOSS_PCT", 0.30),
            time_stop_sec=int(_get_float("SOL_TIME_STOP_SEC", 300)),
            liq_drop_pct=_get_float("SOL_LIQ_DROP_PCT", 0.40),
            monitor_interval_sec=_get_float("SOL_MONITOR_INTERVAL_SEC", 3.0),
            min_sol_in_curve=_get_float("MIN_SOL_IN_CURVE", 0.0),
            max_sol_in_curve=_get_float("MAX_SOL_IN_CURVE", 0.0),
            buy_delay_sec=_get_float("BUY_DELAY_SEC", 0.0),
            momentum_window_sec=_get_float("MOMENTUM_WINDOW_SEC", 0.0),
            require_growth=_get_bool("REQUIRE_GROWTH", False),
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
        if not (0 < self.max_roundtrip_loss_pct < 1):
            errors.append("MAX_ROUNDTRIP_LOSS_PCT deve estar entre 0 e 1.")
        if not (0 <= self.max_top_holder_pct <= 1):
            errors.append("MAX_TOP_HOLDER_PCT deve estar entre 0 e 1 (0 = desligado).")
        if self.stop_loss_pct <= 0 or self.take_profit_pct <= 0:
            errors.append("SOL_STOP_LOSS_PCT e SOL_TAKE_PROFIT_PCT devem ser > 0.")
        if errors:
            raise ValueError("Config Solana inválida:\n- " + "\n- ".join(errors))
