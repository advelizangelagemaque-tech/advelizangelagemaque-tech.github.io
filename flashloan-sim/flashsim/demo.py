"""Modo demonstração: roda na hora, sem internet e sem configurar nada.

Mostra cenários realistas (com reservas inventadas, mas plausíveis) para você VER
como a conta funciona e entender a lição central: o gap que aparece na tela quase
sempre é comido pelas taxas das DEXs + taxa do flash loan + gás. Só um gap grande,
numa rede barata, sobra lucro — e esses são raros e disputadíssimos.
"""

from __future__ import annotations

from .chains import CHAINS
from .simulate import Pool, find_arbitrage


def _fmt(op, chain_name: str) -> str:
    ok = "✅ LUCRO" if op.net_profit > 0 else "❌ prejuízo"
    return (
        f"  Rede {chain_name} | {op.pair}\n"
        f"    Diferença de preço entre DEXs (vitrine): {op.spread_pct:.2f}%\n"
        f"    Melhor empréstimo: {op.borrow_usdc:,.0f} USDC  "
        f"({op.buy_dex} → {op.sell_dex})\n"
        f"    Ganho após taxas das DEXs+flash: {op.gross_profit:+.2f} USDT | "
        f"gás: -{op.gas_usd:.2f}\n"
        f"    >>> Lucro líquido: {op.net_profit:+.2f} USDT   {ok}\n"
    )


# Cenários: (nome, reservas p1, reservas p2, fee). USDC/TOKEN em unidades humanas.
_SCENARIOS = [
    ("Gap minúsculo (0.15%) — o dia a dia real",
     Pool("QuickSwap", 2_000_000, 2_000_000, 30),
     Pool("SushiSwap", 2_000_000, 1_997_000, 30)),
    ("Gap pequeno (0.5%) — aparece às vezes",
     Pool("QuickSwap", 1_000_000, 1_000_000, 30),
     Pool("SushiSwap", 1_000_000, 995_000, 30)),
    ("Gap grande (3%) — raro e muito disputado",
     Pool("QuickSwap", 500_000, 500_000, 30),
     Pool("SushiSwap", 500_000, 485_000, 30)),
]


def run_demo() -> int:
    print("=" * 66)
    print("DEMONSTRAÇÃO — arbitragem com flash loan (só simulação, ZERO risco)")
    print("=" * 66)
    print("Regra: só vale a pena se o Lucro líquido for POSITIVO depois de TUDO.\n")

    barata = CHAINS["polygon"]     # rede barata
    cara = CHAINS["ethereum"]      # rede cara (comparação)

    for titulo, p1, p2 in _SCENARIOS:
        print(f"• {titulo}")
        op_b = find_arbitrage("WMATIC/USDC", p1, p2,
                              flash_fee_bps=barata.flash_fee_bps, gas_usd=barata.gas_usd)
        print(_fmt(op_b, barata.name))

    print("-" * 66)
    print("MESMO gap de 0.5%, mas na Ethereum (gás caro) — repara na virada:")
    p1 = Pool("Uniswap", 1_000_000, 1_000_000, 30)
    p2 = Pool("Sushi",   1_000_000, 995_000, 30)
    op_c = find_arbitrage("WETH/USDC", p1, p2,
                          flash_fee_bps=cara.flash_fee_bps, gas_usd=cara.gas_usd)
    print(_fmt(op_c, cara.name))

    print("=" * 66)
    print("LIÇÃO: o gap de 'vitrine' engana. Taxa de DEX (0.3%+0.3%) + flash + gás")
    print("comem quase tudo. Gaps grandes o bastante para sobrar lucro são raros e")
    print("os bots profissionais os pegam no mesmo bloco. Por isso: medir antes de")
    print("arriscar. O modo --scan faz isso com preços REAIS das DEXs.")
    print("=" * 66)
    return 0
