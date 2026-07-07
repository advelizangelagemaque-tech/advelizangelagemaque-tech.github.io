"""Configuração das redes (foco em redes BARATAS) e custo de gás estimado.

O gás muda tudo na arbitragem: numa rede cara (Ethereum) um gap pequeno vira
prejuízo; numa L2 barata o mesmo gap pode sobrar lucro. Aqui ficam estimativas
razoáveis do custo em USD de UMA transação de arbitragem (~350k de gas).
Ajuste `gas_usd` conforme a rede estiver no momento.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Chain:
    key: str
    name: str
    native: str            # moeda de gás
    rpc_env: str           # nome da variável de ambiente com o RPC
    gas_usd: float         # custo estimado de 1 arbitragem, em USD
    flash_fee_bps: float   # taxa típica de flash loan na rede (Aave v3 = 5)


# Redes baratas primeiro (recomendadas para começar). Ethereum incluída só para
# comparação — o gás altíssimo dela costuma inviabilizar arbitragem de varejo.
CHAINS: dict[str, Chain] = {
    "polygon":  Chain("polygon",  "Polygon PoS", "POL",  "RPC_POLYGON",  0.03, 5),
    "base":     Chain("base",     "Base",        "ETH",  "RPC_BASE",     0.02, 5),
    "arbitrum": Chain("arbitrum", "Arbitrum One","ETH",  "RPC_ARBITRUM", 0.08, 5),
    "bsc":      Chain("bsc",      "BNB Chain",   "BNB",  "RPC_BSC",      0.20, 0),
    "optimism": Chain("optimism", "Optimism",    "ETH",  "RPC_OPTIMISM", 0.05, 5),
    "ethereum": Chain("ethereum", "Ethereum L1", "ETH",  "RPC_ETHEREUM", 25.0, 5),
}


def get_chain(key: str) -> Chain:
    k = key.strip().lower()
    if k not in CHAINS:
        raise SystemExit(f"Rede desconhecida: {key}. Opções: {', '.join(CHAINS)}")
    return CHAINS[k]


# Provedores de flash loan por rede, com a taxa em pontos-base. A escolha certa
# MUDA a conta: a Balancer empresta de GRAÇA (0%), enquanto a Aave cobra 0.05%.
# Usar o mais barato disponível melhora a borda — por isso pegamos o menor.
FLASH_PROVIDERS: dict[str, list[tuple[str, float]]] = {
    "polygon":  [("Balancer", 0), ("Aave v3", 5)],
    "arbitrum": [("Balancer", 0), ("Aave v3", 5)],
    "base":     [("Balancer", 0), ("Aave v3", 5)],
    "optimism": [("Balancer", 0), ("Aave v3", 5)],
    "bsc":      [("Aave v3", 5)],                       # Balancer não opera na BSC
    "ethereum": [("Balancer", 0), ("Maker DAI", 0), ("Aave v3", 5)],
}


def best_flash_provider(chain_key: str) -> tuple[str, float]:
    """(nome, taxa_bps) do flash loan mais barato disponível na rede."""
    provs = FLASH_PROVIDERS.get(chain_key, [("Aave v3", 5)])
    name, fee = min(provs, key=lambda p: p[1])
    return name, fee
