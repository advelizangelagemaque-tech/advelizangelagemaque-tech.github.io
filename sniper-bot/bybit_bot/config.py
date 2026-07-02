"""Configuração do agente Bybit (derivativos USDT)."""

from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # pragma: no cover
    pass


def _f(name, default):
    v = os.getenv(name)
    return float(v) if v not in (None, "") else default


def _i(name, default):
    v = os.getenv(name)
    return int(v) if v not in (None, "") else default


def _b(name, default):
    v = os.getenv(name)
    return default if v is None else v.strip().lower() in {"1", "true", "yes", "sim"}


@dataclass
class BybitConfig:
    api_key: str
    api_secret: str
    use_testnet: bool
    leverage: int
    margin_usdt: float           # margem por trade (tamanho da posição = margem * leverage)
    tp_roi: float                # take-profit em ROI (0.30 = +30%)
    sl_roi: float                # stop-loss em ROI (0.15 = -15%)
    min_24h: float
    max_24h: float
    dip_min: float
    dip_max: float
    max_positions: int
    poll_interval_sec: float
    # análise de mercado (filtro macro)
    use_market_filter: bool = True
    btc_min_24h: float = -0.03      # se BTC cair mais que isso em 24h, pausa compras
    breadth_min: float = 0.35       # fração mínima de perps no positivo (mercado "risk-on")
    # ajuste automático (aprendizado) — travado até ter amostra suficiente
    autotune: bool = False
    autotune_min_trades: int = 20
    # cooldown: tempo sem re-entrar num token depois que ele fecha (evita faca caindo)
    cooldown_sec: float = 3600.0
    # filtro técnico (RSI + EMA) na entrada
    use_ta_filter: bool = True
    ta_timeframe: str = "5m"
    rsi_period: int = 14
    rsi_min: float = 40.0
    rsi_max: float = 72.0
    ema_len: int = 20

    @classmethod
    def load(cls) -> "BybitConfig":
        # RSA: se BYBIT_API_PRIVATE_KEY_PATH aponta para um .pem, usamos o
        # conteúdo como "secret" (o ccxt detecta PRIVATE KEY e assina com RSA).
        # Caso contrário, usamos BYBIT_API_SECRET (chave HMAC).
        secret = os.getenv("BYBIT_API_SECRET", "")
        priv_path = os.getenv("BYBIT_API_PRIVATE_KEY_PATH", "").strip()
        if priv_path:
            path = os.path.expanduser(priv_path)
            if not os.path.exists(path):
                raise ValueError(f"BYBIT_API_PRIVATE_KEY_PATH não encontrado: {path}")
            with open(path, encoding="utf-8") as f:
                secret = f.read()

        cfg = cls(
            api_key=os.getenv("BYBIT_API_KEY", ""),
            api_secret=secret,
            use_testnet=_b("BYBIT_TESTNET", True),
            leverage=_i("BYBIT_LEVERAGE", 5),
            margin_usdt=_f("BYBIT_MARGIN_USDT", 10.0),
            tp_roi=_f("BYBIT_TP_ROI", 0.30),
            sl_roi=_f("BYBIT_SL_ROI", 0.15),
            min_24h=_f("BYBIT_MIN_24H", 0.20),
            max_24h=_f("BYBIT_MAX_24H", 0.50),
            dip_min=_f("BYBIT_DIP_MIN", 0.03),
            dip_max=_f("BYBIT_DIP_MAX", 0.10),
            max_positions=_i("BYBIT_MAX_POSITIONS", 1),
            poll_interval_sec=_f("BYBIT_POLL_SEC", 20.0),
            use_market_filter=_b("BYBIT_USE_MARKET_FILTER", True),
            btc_min_24h=_f("BYBIT_BTC_MIN_24H", -0.03),
            breadth_min=_f("BYBIT_BREADTH_MIN", 0.35),
            autotune=_b("BYBIT_AUTOTUNE", False),
            autotune_min_trades=_i("BYBIT_AUTOTUNE_MIN_TRADES", 20),
            cooldown_sec=_f("BYBIT_COOLDOWN_SEC", 3600.0),
            use_ta_filter=_b("BYBIT_USE_TA_FILTER", True),
            ta_timeframe=os.getenv("BYBIT_TA_TIMEFRAME", "5m") or "5m",
            rsi_period=_i("BYBIT_RSI_PERIOD", 14),
            rsi_min=_f("BYBIT_RSI_MIN", 40.0),
            rsi_max=_f("BYBIT_RSI_MAX", 72.0),
            ema_len=_i("BYBIT_EMA_LEN", 20),
        )
        cfg.validate()
        return cfg

    def validate(self) -> None:
        errs = []
        if not (1 <= self.leverage <= 25):
            errs.append("BYBIT_LEVERAGE deve estar entre 1 e 25.")
        if self.margin_usdt <= 0:
            errs.append("BYBIT_MARGIN_USDT deve ser > 0.")
        if not (0 < self.sl_roi < 1):
            errs.append("BYBIT_SL_ROI deve estar entre 0 e 1. Stop-loss é obrigatório.")
        if self.tp_roi <= 0:
            errs.append("BYBIT_TP_ROI deve ser > 0.")
        if self.max_positions < 1:
            errs.append("BYBIT_MAX_POSITIONS deve ser >= 1.")
        if self.dip_max <= self.dip_min:
            errs.append("BYBIT_DIP_MAX deve ser maior que BYBIT_DIP_MIN.")
        if errs:
            raise ValueError("Config Bybit inválida:\n- " + "\n- ".join(errs))

    def require_keys(self) -> None:
        if not self.api_key or not self.api_secret:
            raise ValueError("Modo real exige BYBIT_API_KEY/BYBIT_API_SECRET (chave da SUBCONTA, "
                             "só trade, sem saque). Use --dry-run para simular sem chaves.")
