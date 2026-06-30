"""Carrega e valida a configuração a partir do arquivo .env."""

from __future__ import annotations

import os
from dataclasses import dataclass

try:  # python-dotenv é opcional (útil em dev/testes sem a dependência)
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "sim"}


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw not in (None, "") else default


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw not in (None, "") else default


@dataclass
class Config:
    exchange: str
    api_key: str
    api_secret: str
    use_testnet: bool
    margin_usdt: float
    leverage: int
    take_profit_pct: float
    stop_loss_pct: float
    quote_asset: str
    poll_interval_ms: int
    max_trades: int
    # Filtro de qualidade (0 = desligado)
    max_spread_pct: float
    min_book_depth_usdt: float
    min_quote_volume: float
    # Trailing stop
    use_trailing: bool
    trailing_callback_pct: float
    # Cooldown entre entradas (segundos)
    cooldown_seconds: int
    # Alertas Telegram (vazio = desligado)
    telegram_token: str
    telegram_chat_id: str

    @classmethod
    def load(cls) -> "Config":
        cfg = cls(
            exchange=os.getenv("EXCHANGE", "binance").strip().lower(),
            api_key=os.getenv("BINANCE_API_KEY", ""),
            api_secret=os.getenv("BINANCE_API_SECRET", ""),
            use_testnet=_get_bool("USE_TESTNET", True),
            margin_usdt=_get_float("MARGIN_USDT", 20.0),
            leverage=_get_int("LEVERAGE", 3),
            take_profit_pct=_get_float("TAKE_PROFIT_PCT", 0.10),
            stop_loss_pct=_get_float("STOP_LOSS_PCT", 0.05),
            quote_asset=os.getenv("QUOTE_ASSET", "USDT").upper(),
            poll_interval_ms=_get_int("POLL_INTERVAL_MS", 500),
            max_trades=_get_int("MAX_TRADES", 1),
            max_spread_pct=_get_float("MAX_SPREAD_PCT", 0.03),
            min_book_depth_usdt=_get_float("MIN_BOOK_DEPTH_USDT", 1000.0),
            min_quote_volume=_get_float("MIN_QUOTE_VOLUME", 0.0),
            use_trailing=_get_bool("USE_TRAILING", False),
            trailing_callback_pct=_get_float("TRAILING_CALLBACK_PCT", 0.01),
            cooldown_seconds=_get_int("COOLDOWN_SECONDS", 0),
            telegram_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip(),
        )
        cfg.validate()
        return cfg

    def validate(self) -> None:
        """Falha cedo e alto se a configuração for perigosa ou inválida."""
        errors = []
        if not self.exchange:
            errors.append("EXCHANGE não pode ser vazio (ex.: binance, bybit, okx).")
        # Chaves NÃO são exigidas aqui: paper/dry só leem dados públicos.
        # A exigência de chaves para o modo live é feita em require_keys_for_live().
        if self.margin_usdt <= 0:
            errors.append("MARGIN_USDT precisa ser > 0.")
        if not (1 <= self.leverage <= 125):
            errors.append("LEVERAGE precisa estar entre 1 e 125.")
        if not (0 < self.stop_loss_pct < 1):
            errors.append("STOP_LOSS_PCT precisa estar entre 0 e 1. Stop-loss é obrigatório.")
        if not (0 < self.take_profit_pct < 5):
            errors.append("TAKE_PROFIT_PCT precisa estar entre 0 e 5.")
        if self.poll_interval_ms < 100:
            errors.append("POLL_INTERVAL_MS muito baixo pode levar a ban por rate-limit (mín. 100).")
        if self.max_spread_pct < 0 or self.min_book_depth_usdt < 0 or self.min_quote_volume < 0:
            errors.append("Limites do filtro de qualidade não podem ser negativos.")
        if self.use_trailing and not (0.001 <= self.trailing_callback_pct <= 0.05):
            errors.append("TRAILING_CALLBACK_PCT deve estar entre 0.001 (0.1%) e 0.05 (5%) — limite da Binance.")
        if self.cooldown_seconds < 0:
            errors.append("COOLDOWN_SECONDS não pode ser negativo.")
        if errors:
            raise ValueError("Configuração inválida:\n- " + "\n- ".join(errors))

    def require_keys_for_live(self) -> None:
        """Modo live precisa de chaves (paper/dry não, pois só leem dados públicos)."""
        if not self.api_key or not self.api_secret:
            raise ValueError(
                "Modo live exige BINANCE_API_KEY/BINANCE_API_SECRET no .env. "
                "Para apenas validar a estratégia sem chaves, use --paper."
            )
