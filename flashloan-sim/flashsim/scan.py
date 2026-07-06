"""Escaneador AO VIVO: lê as reservas REAIS das pools na blockchain e mede a
arbitragem. Somente LEITURA — nenhuma transação, nenhuma chave privada.

Precisa de web3 instalado e de um RPC (endereço de um nó) na variável de ambiente
da rede (ex: RPC_POLYGON). Se algo faltar, ele avisa e não quebra.
"""

from __future__ import annotations

import itertools
import json
import os

from .chains import get_chain
from .simulate import Pool, find_arbitrage

# ABIs mínimas (só o que a gente lê).
_PAIR_ABI = [
    {"name": "getReserves", "outputs": [
        {"type": "uint112", "name": "_reserve0"},
        {"type": "uint112", "name": "_reserve1"},
        {"type": "uint32", "name": "_blockTimestampLast"}],
     "inputs": [], "stateMutability": "view", "type": "function"},
    {"name": "token0", "outputs": [{"type": "address"}], "inputs": [],
     "stateMutability": "view", "type": "function"},
    {"name": "token1", "outputs": [{"type": "address"}], "inputs": [],
     "stateMutability": "view", "type": "function"},
]
_ERC20_ABI = [
    {"name": "decimals", "outputs": [{"type": "uint8"}], "inputs": [],
     "stateMutability": "view", "type": "function"},
]


def _connect(chain):
    try:
        from web3 import Web3
    except ImportError:
        raise SystemExit(
            "web3 não está instalado. Rode:  pip install web3\n"
            "(é só leitura — não precisa de chave nenhuma).")
    rpc = os.getenv(chain.rpc_env, "").strip()
    if not rpc:
        raise SystemExit(
            f"Falta o RPC da rede {chain.name}. Defina a variável {chain.rpc_env} "
            f"com o endereço de um nó público, por exemplo:\n"
            f"  export {chain.rpc_env}=https://polygon-rpc.com")
    w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 20}))
    if not w3.is_connected():
        raise SystemExit(f"Não consegui conectar no RPC ({rpc}). Verifique o endereço.")
    return w3, Web3


def _read_pool(w3, Web3, addr, usdc_addr, token_addr, usdc_dec, token_dec, dex, fee_bps):
    """Lê as reservas reais de uma pool e devolve um Pool normalizado (unidades humanas)."""
    c = w3.eth.contract(address=Web3.to_checksum_address(addr), abi=_PAIR_ABI)
    r0, r1, _ = c.functions.getReserves().call()
    t0 = c.functions.token0().call().lower()
    if t0 == usdc_addr.lower():
        usdc_raw, token_raw = r0, r1
    else:
        usdc_raw, token_raw = r1, r0
    return Pool(dex=dex, usdc=usdc_raw / 10 ** usdc_dec,
                token=token_raw / 10 ** token_dec, fee_bps=fee_bps)


def _decimals(w3, Web3, addr):
    c = w3.eth.contract(address=Web3.to_checksum_address(addr), abi=_ERC20_ABI)
    return c.functions.decimals().call()


def scan(config_path: str) -> int:
    with open(config_path, encoding="utf-8") as f:
        cfg = json.load(f)
    chain = get_chain(cfg["chain"])
    gas_usd = float(cfg.get("gas_usd", chain.gas_usd))
    w3, Web3 = _connect(chain)

    print("=" * 66)
    print(f"ESCANEANDO {chain.name} (só leitura) | gás estimado ${gas_usd:.3f} | "
          f"flash {chain.flash_fee_bps/100:.2f}%")
    print("=" * 66)

    achou = 0
    for pair in cfg["pairs"]:
        name = pair["name"]
        usdc_addr, token_addr = pair["usdc"], pair["token"]
        try:
            usdc_dec = _decimals(w3, Web3, usdc_addr)
            token_dec = _decimals(w3, Web3, token_addr)
            pools = []
            for pl in pair["pools"]:
                pools.append(_read_pool(w3, Web3, pl["address"], usdc_addr, token_addr,
                                        usdc_dec, token_dec, pl["dex"],
                                        pl.get("fee_bps", 30)))
        except Exception as exc:  # noqa: BLE001
            print(f"• {name}: pulei (erro ao ler pools: {str(exc)[:80]})")
            continue

        best = None
        for a, b in itertools.combinations(pools, 2):
            op = find_arbitrage(name, a, b, flash_fee_bps=chain.flash_fee_bps,
                                gas_usd=gas_usd)
            if best is None or op.net_profit > best.net_profit:
                best = op
        if best is None:
            continue
        marca = "✅ LUCRO" if best.net_profit > 0 else "—"
        print(f"• {name}: spread {best.spread_pct:.3f}% | "
              f"empréstimo ~{best.borrow_usdc:,.0f} | "
              f"líquido {best.net_profit:+.2f} USDT  {marca}")
        if best.net_profit > 0:
            achou += 1

    print("-" * 66)
    print(f"Oportunidades com lucro líquido POSITIVO agora: {achou}")
    print("(Lembre: mesmo positivo na leitura, os bots profissionais competem pelo")
    print(" mesmo gap no mesmo bloco. Isto é medição, não promessa de execução.)")
    print("=" * 66)
    return 0
