"""Simulação de GRID de FUTUROS sobre candles. Pura e testável.

O grid põe ordens de compra abaixo e de venda acima, em níveis fixos dentro de uma
faixa. Cada 'ida-e-volta' (compra num nível, vende no de cima) embolsa o passo.
Ganha em mercado de LADO; sofre em TENDÊNCIA. E como é FUTUROS (com alavancagem),
se o preço romper a faixa e continuar, a posição acumula de um lado só e pode ser
LIQUIDADA — é isso que a gente mede aqui ANTES de arriscar dinheiro.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GridParams:
    lower: float                  # piso da faixa
    upper: float                  # teto da faixa
    n_grids: int = 30             # número de níveis
    leverage: int = 2             # alavancagem (BAIXA! 2x recomendado)
    capital: float = 100.0        # margem (USDT)
    fee_bps: float = 2.0          # taxa de maker por execução (grid usa ordem limite)
    geometric: bool = True        # espaçamento em % (melhor p/ cripto) vs aritmético


def _levels(p: GridParams) -> list:
    if p.geometric and p.lower > 0:
        r = (p.upper / p.lower) ** (1 / p.n_grids)
        return [p.lower * (r ** i) for i in range(p.n_grids + 1)]
    step = (p.upper - p.lower) / p.n_grids
    return [p.lower + i * step for i in range(p.n_grids + 1)]


def simulate_grid(candles: list, p: GridParams) -> dict:
    """Roda o grid nos candles [ts,o,h,l,c,v]. Devolve resumo (lucro, execuções,
    se LIQUIDOU, drawdown). Aproximação honesta em candle diário/horário."""
    levels = _levels(p)
    notional_per = p.capital * p.leverage / p.n_grids     # notional por nível
    fee = p.fee_bps / 10_000.0
    inv = 0.0                                             # estoque (unidades)
    cash = 0.0                                            # fluxo de caixa das ordens
    fills = 0
    liquidated = False
    price0 = candles[0][1] if candles else 0.0
    pending = ["buy" if lv < price0 else "sell" for lv in levels]   # ordem em cada nível
    peak = p.capital
    max_dd = 0.0
    for c in candles:
        _, o, hi, lo, cl, _ = c[:6]
        for i, lv in enumerate(levels):
            if pending[i] == "buy" and lo <= lv:               # tocou a compra
                u = notional_per / lv
                cash -= lv * u * (1 + fee)
                inv += u
                fills += 1
                pending[i] = None
                if i + 1 <= p.n_grids:
                    pending[i + 1] = "sell"                     # arma a venda acima
            elif pending[i] == "sell" and hi >= lv:            # tocou a venda
                u = notional_per / lv
                cash += lv * u * (1 - fee)
                inv -= u
                fills += 1
                pending[i] = None
                if i - 1 >= 0:
                    pending[i - 1] = "buy"                      # arma a compra abaixo
        equity = p.capital + cash + inv * cl                   # margem + P&L (fluxo + estoque)
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak if peak > 0 else 0.0)
        if equity <= 0:                                        # perdeu toda a margem
            liquidated = True
            break
    last = candles[-1][4] if candles else 0.0
    final_equity = 0.0 if liquidated else p.capital + cash + inv * last
    net = final_equity - p.capital
    return {"net": net, "final_equity": final_equity, "fills": fills,
            "liquidated": liquidated, "max_drawdown": max_dd,
            "end_inventory_usdt": inv * last, "return_pct": net / p.capital * 100}


# ---- demonstração --------------------------------------------------------

def _ranging(n: int = 400, base: float = 100.0, amp: float = 0.04) -> list:
    import math
    out, prev = [], base
    for i in range(n):
        mid = base * (1 + amp * math.sin(i / 6.0))
        o, c = prev, mid
        out.append([i, o, max(o, c) * 1.003, min(o, c) * 0.997, c, 1])
        prev = mid
    return out


def _crash(n: int = 200, base: float = 100.0, floor: float = 60.0) -> list:
    # queda firme e reta de `base` até `floor` (rompe a faixa por baixo e continua)
    out, prev = [], base
    for i in range(n):
        mid = base + (floor - base) * (i / (n - 1))
        o, c = prev, mid
        out.append([i, o, max(o, c), min(o, c), c, 1])
        prev = mid
    return out


def _fmt(title: str, st: dict) -> str:
    if st["liquidated"]:
        tag = "💥 LIQUIDADO (perdeu a margem)"
    else:
        tag = "✅ LUCRO" if st["net"] > 0 else "❌ prejuízo"
    return (f"• {title}\n"
            f"    Execuções: {st['fills']} | estoque no fim: {st['end_inventory_usdt']:+.1f} USDT\n"
            f"    Pior queda do capital: -{st['max_drawdown']*100:.0f}%\n"
            f"    >>> Resultado: {st['net']:+.2f} USDT ({st['return_pct']:+.1f}%)   {tag}\n")


def run_grid_demo() -> int:
    print("=" * 66)
    print("DEMONSTRAÇÃO — GRID de futuros (só simulação, ZERO risco)")
    print("=" * 66)
    print("Capital $100 em todos os casos.\n")
    print(_fmt("Mercado DE LADO, faixa certa, alavancagem 2x — o cenário bom",
               simulate_grid(_ranging(), GridParams(96, 104, 30, 2, 100))))
    print(_fmt("CRASH pra fora da faixa, alavancagem BAIXA 2x — sobrevive, mas perde",
               simulate_grid(_crash(), GridParams(70, 110, 30, 2, 100))))
    print(_fmt("CRASH pra fora da faixa, alavancagem ALTA 5x — o perigo real",
               simulate_grid(_crash(), GridParams(70, 110, 30, 5, 100))))
    print("=" * 66)
    print("LIÇÃO: o grid é uma máquina de colher oscilação — ótima em faixa, e")
    print("PERIGOSA em tendência. Alavancagem BAIXA (2x) e faixa larga te salvam da")
    print("liquidação; alavancagem alta te quebra quando o preço rompe. Por isso:")
    print("spot ou 2x, faixa larga e stop. O --grid mede isso em preços REAIS.")
    print("=" * 66)
    return 0
