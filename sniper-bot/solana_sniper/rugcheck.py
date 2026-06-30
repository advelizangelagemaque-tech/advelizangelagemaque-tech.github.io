"""Camada 1 anti-rug: checagens ANTES de comprar.

- Simulação de venda (round-trip): cota comprar e depois VENDER de volta. Se
  não há rota de venda ou a perda ida-e-volta é grande demais, é honeypot/
  taxa abusiva ("compra e não vende"). É o teste mais forte de vendabilidade.
- Concentração de holders: se uma carteira detém fatia grande do supply, há
  risco de dump. (Obs.: em tokens pump.fun pré-graduação a maior conta costuma
  ser a própria curva de liquidez — por isso o limite é configurável/0=off.)
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import WSOL_MINT
from .execute import get_quote


@dataclass
class RugVerdict:
    ok: bool
    reasons: list[str]
    metrics: dict


def simulate_round_trip(input_lamports: int, mint: str, slippage_bps: int) -> dict:
    """Compra simulada SOL->token e venda simulada token->SOL.

    Retorna métricas: token_out, sol_back, roundtrip_ratio, loss_pct, sellable.
    """
    try:
        buy = get_quote(WSOL_MINT, mint, input_lamports, slippage_bps)
    except Exception:  # noqa: BLE001  (token muito novo / fora do Jupiter ainda)
        return {"sellable": False, "loss_pct": 1.0, "token_out": 0, "sol_back": 0,
                "roundtrip_ratio": 0.0, "reason": "sem rota de compra (token novo demais?)"}
    token_out = int(buy.get("outAmount") or 0)
    if token_out <= 0:
        return {"sellable": False, "loss_pct": 1.0, "token_out": 0, "sol_back": 0,
                "roundtrip_ratio": 0.0, "reason": "sem rota de compra"}
    try:
        sell = get_quote(mint, WSOL_MINT, token_out, slippage_bps)
    except Exception:  # noqa: BLE001  (sem rota de venda = honeypot)
        return {"sellable": False, "loss_pct": 1.0, "token_out": token_out, "sol_back": 0,
                "roundtrip_ratio": 0.0, "reason": "sem rota de venda (honeypot)"}
    sol_back = int(sell.get("outAmount") or 0)
    ratio = sol_back / input_lamports if input_lamports else 0.0
    return {
        "sellable": sol_back > 0,
        "loss_pct": max(0.0, 1.0 - ratio),
        "token_out": token_out, "sol_back": sol_back, "roundtrip_ratio": ratio,
        "reason": "",
    }


def check_holder_concentration(rpc, mint: str) -> dict:
    """Fração do supply na maior carteira."""
    supply = int((rpc.get_token_supply(mint).get("value") or {}).get("amount") or 0)
    accounts = rpc.get_token_largest_accounts(mint).get("value") or []
    top = int(accounts[0]["amount"]) if accounts else 0
    top_pct = (top / supply) if supply else 1.0
    return {"supply": supply, "top_holder_pct": top_pct, "holders_listed": len(accounts)}


def assess_pre_buy(rpc, mint: str, cfg, probe_lamports: int) -> RugVerdict:
    """Junta as checagens de pré-compra num veredito único."""
    reasons: list[str] = []
    metrics: dict = {}

    rt = simulate_round_trip(probe_lamports, mint, cfg.slippage_bps)
    metrics["roundtrip"] = rt
    if not rt["sellable"]:
        reasons.append(f"não-vendável: {rt['reason'] or 'honeypot'}")
    elif rt["loss_pct"] > cfg.max_roundtrip_loss_pct:
        reasons.append(
            f"perda ida-e-volta {rt['loss_pct']:.0%} > máx {cfg.max_roundtrip_loss_pct:.0%}"
        )

    if cfg.max_top_holder_pct > 0:
        hc = check_holder_concentration(rpc, mint)
        metrics["holders"] = hc
        if hc["top_holder_pct"] > cfg.max_top_holder_pct:
            reasons.append(
                f"maior holder tem {hc['top_holder_pct']:.0%} > máx {cfg.max_top_holder_pct:.0%}"
            )

    return RugVerdict(ok=not reasons, reasons=reasons, metrics=metrics)
