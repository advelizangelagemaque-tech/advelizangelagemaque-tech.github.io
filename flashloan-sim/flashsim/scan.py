"""Escaneador AO VIVO: lê as reservas REAIS das pools na blockchain e mede a
arbitragem. Somente LEITURA — nenhuma transação, nenhuma chave privada.

Descobre o endereço de cada pool sozinho, perguntando ao 'factory' de cada DEX
(getPair) — assim não dependemos de colar endereços de pool à mão. Precisa de web3
e de um RPC (nó) na variável de ambiente da rede (ex: RPC_POLYGON).
"""

from __future__ import annotations

import itertools
import json
import os

from .chains import get_chain
from .simulate import Pool, find_arbitrage
from .triangular import Leg, evaluate_cycle

ZERO_ADDR = "0x0000000000000000000000000000000000000000"

# ABIs mínimas (só o que a gente lê).
_FACTORY_ABI = [
    {"name": "getPair", "inputs": [{"type": "address"}, {"type": "address"}],
     "outputs": [{"type": "address"}], "stateMutability": "view", "type": "function"},
]
_PAIR_ABI = [
    {"name": "getReserves", "outputs": [
        {"type": "uint112", "name": "_reserve0"},
        {"type": "uint112", "name": "_reserve1"},
        {"type": "uint32", "name": "_blockTimestampLast"}],
     "inputs": [], "stateMutability": "view", "type": "function"},
    {"name": "token0", "outputs": [{"type": "address"}], "inputs": [],
     "stateMutability": "view", "type": "function"},
]
_ERC20_ABI = [
    {"name": "decimals", "outputs": [{"type": "uint8"}], "inputs": [],
     "stateMutability": "view", "type": "function"},
]


def orient_reserves(token0: str, usdc_addr: str, r0: float, r1: float,
                    usdc_dec: int, token_dec: int) -> tuple[float, float]:
    """Descobre qual reserva é USDC e qual é o token, e normaliza para unidades
    humanas (divide pelos decimais). Pura e testável."""
    if token0.lower() == usdc_addr.lower():
        usdc_raw, token_raw = r0, r1
    else:
        usdc_raw, token_raw = r1, r0
    return usdc_raw / 10 ** usdc_dec, token_raw / 10 ** token_dec


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
            f"Falta o RPC da rede {chain.name}. Defina a variável {chain.rpc_env}, ex:\n"
            f"  export {chain.rpc_env}=https://polygon-rpc.com")
    w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 20}))
    if not w3.is_connected():
        raise SystemExit(f"Não consegui conectar no RPC ({rpc}). Verifique o endereço.")
    return w3, Web3


def _decimals(w3, Web3, addr):
    c = w3.eth.contract(address=Web3.to_checksum_address(addr), abi=_ERC20_ABI)
    return c.functions.decimals().call()


def _read_pool(w3, Web3, pool_addr, usdc_addr, token_addr, usdc_dec, token_dec,
               dex, fee_bps):
    c = w3.eth.contract(address=Web3.to_checksum_address(pool_addr), abi=_PAIR_ABI)
    r0, r1, _ = c.functions.getReserves().call()
    t0 = c.functions.token0().call()
    usdc, token = orient_reserves(t0, usdc_addr, r0, r1, usdc_dec, token_dec)
    return Pool(dex=dex, usdc=usdc, token=token, fee_bps=fee_bps)


def scan(config_path: str) -> int:
    with open(config_path, encoding="utf-8") as f:
        cfg = json.load(f)
    chain = get_chain(cfg["chain"])
    gas_usd = float(cfg.get("gas_usd", chain.gas_usd))
    dexes = cfg["dexes"]
    w3, Web3 = _connect(chain)

    print("=" * 66)
    print(f"ESCANEANDO {chain.name} (só leitura) | gás ~${gas_usd:.3f} | "
          f"flash {chain.flash_fee_bps / 100:.2f}% | DEXs: "
          f"{', '.join(d['name'] for d in dexes)}")
    print("=" * 66)

    achou = 0
    for pair in cfg["pairs"]:
        name = pair["name"]
        usdc_addr, token_addr = pair["usdc"], pair["token"]
        try:
            usdc_dec = _decimals(w3, Web3, usdc_addr)
            token_dec = _decimals(w3, Web3, token_addr)
            pools = []
            for dex in dexes:
                fac = w3.eth.contract(address=Web3.to_checksum_address(dex["factory"]),
                                      abi=_FACTORY_ABI)
                pool_addr = fac.functions.getPair(
                    Web3.to_checksum_address(usdc_addr),
                    Web3.to_checksum_address(token_addr)).call()
                if pool_addr == ZERO_ADDR:
                    continue                       # essa DEX não tem essa dupla
                pools.append(_read_pool(w3, Web3, pool_addr, usdc_addr, token_addr,
                                        usdc_dec, token_dec, dex["name"],
                                        dex.get("fee_bps", 30)))
        except Exception as exc:  # noqa: BLE001
            print(f"• {name}: pulei (erro ao ler: {str(exc)[:80]})")
            continue

        if len(pools) < 2:
            print(f"• {name}: só achei {len(pools)} pool — preciso de 2+ para arbitrar.")
            continue

        best = None
        for a, b in itertools.combinations(pools, 2):
            op = find_arbitrage(name, a, b, flash_fee_bps=chain.flash_fee_bps,
                                gas_usd=gas_usd)
            if best is None or op.net_profit > best.net_profit:
                best = op
        marca = "✅ LUCRO" if best.net_profit > 0 else "—"
        print(f"• {name}: spread {best.spread_pct:.3f}% | "
              f"empréstimo ~{best.borrow_usdc:,.0f} | "
              f"líquido {best.net_profit:+.2f} USDT  {marca}")
        if best.net_profit > 0:
            achou += 1

    print("-" * 66)
    print(f"Oportunidades com lucro líquido POSITIVO agora: {achou}")
    print("(Mesmo positivo na leitura, os bots profissionais disputam o mesmo gap")
    print(" no mesmo bloco. Isto é medição honesta, não promessa de execução.)")
    print("=" * 66)
    return 0


# ---- caça à fresta: arbitragem triangular / em ciclo -----------------------

def _read_all_pools(w3, Web3, dexes, tokens, decimals):
    """Descobre TODAS as pools (via factory.getPair) entre os tokens do config, em
    todas as DEXs, e lê as reservas. Retorna {frozenset({symA,symB}): [registros]}."""
    syms = list(tokens)
    pools: dict = {}
    for i in range(len(syms)):
        for j in range(i + 1, len(syms)):
            sa, sb = syms[i], syms[j]
            recs = []
            for dex in dexes:
                try:
                    fac = w3.eth.contract(address=Web3.to_checksum_address(dex["factory"]),
                                          abi=_FACTORY_ABI)
                    addr = fac.functions.getPair(Web3.to_checksum_address(tokens[sa]),
                                                 Web3.to_checksum_address(tokens[sb])).call()
                    if addr == ZERO_ADDR:
                        continue
                    c = w3.eth.contract(address=Web3.to_checksum_address(addr), abi=_PAIR_ABI)
                    r0, r1, _ = c.functions.getReserves().call()
                    t0 = c.functions.token0().call()
                    res_a, res_b = orient_reserves(t0, tokens[sa], r0, r1,
                                                   decimals[sa], decimals[sb])
                    if res_a <= 0 or res_b <= 0:
                        continue
                    recs.append({"dex": dex["name"], "a": sa, "b": sb, "res_a": res_a,
                                 "res_b": res_b, "fee": dex.get("fee_bps", 30)})
                except Exception:  # noqa: BLE001
                    continue
            if recs:
                pools[frozenset((sa, sb))] = recs
    return pools


def _enumerate_cycles(base, tokens, pools):
    """Monta os ciclos possíveis a partir da moeda base (2 e 3 pernas)."""
    others = [s for s in tokens if s != base]
    cycles = []
    # 2 pernas: base -> A -> base usando DUAS pools diferentes do mesmo par (2 DEXs)
    for a in others:
        recs = pools.get(frozenset((base, a)), [])
        for r1 in recs:
            for r2 in recs:
                if r1 is r2:
                    continue
                cycles.append(([base, a, base], [r1, r2]))
    # 3 pernas: base -> A -> B -> base
    for a in others:
        if frozenset((base, a)) not in pools:
            continue
        for b in others:
            if b == a or frozenset((a, b)) not in pools or frozenset((b, base)) not in pools:
                continue
            for r1 in pools[frozenset((base, a))]:
                for r2 in pools[frozenset((a, b))]:
                    for r3 in pools[frozenset((b, base))]:
                        cycles.append(([base, a, b, base], [r1, r2, r3]))
    return cycles


def _legs_from(path, recs):
    legs = []
    for k, rec in enumerate(recs):
        tin, tout = path[k], path[k + 1]
        if rec["a"] == tin:
            rin, rout = rec["res_a"], rec["res_b"]
        else:
            rin, rout = rec["res_b"], rec["res_a"]
        legs.append(Leg(rec["dex"], tin, tout, rin, rout, rec["fee"]))
    return legs


def scan_triangular(config_path: str, log_path: str | None = None) -> int:
    """Caça frestas em ciclos (triangular) entre vários tokens e DEXs. Só leitura."""
    import time
    with open(config_path, encoding="utf-8") as f:
        cfg = json.load(f)
    chain = get_chain(cfg["chain"])
    gas_usd = float(cfg.get("gas_usd", chain.gas_usd))
    base = cfg["base"]
    tokens = cfg["tokens"]
    dexes = cfg["dexes"]
    w3, Web3 = _connect(chain)

    print("=" * 72)
    print(f"CAÇA À FRESTA (triangular) {chain.name} | base {base} | "
          f"{len(tokens)} tokens x {len(dexes)} DEXs | gás ~${gas_usd:.3f}")
    print("=" * 72)

    decimals = {}
    for sym, addr in tokens.items():
        try:
            decimals[sym] = _decimals(w3, Web3, addr)
        except Exception as exc:  # noqa: BLE001
            print(f"  (não li decimais de {sym}: {str(exc)[:50]}) — removido")
    tokens = {s: a for s, a in tokens.items() if s in decimals}

    pools = _read_all_pools(w3, Web3, dexes, tokens, decimals)
    cycles = _enumerate_cycles(base, tokens, pools)
    print(f"Pools encontradas: {sum(len(v) for v in pools.values())} | "
          f"ciclos avaliados: {len(cycles)}")
    print("-" * 72)

    results = []
    for path, recs in cycles:
        op = evaluate_cycle(_legs_from(path, recs), gas_usd)
        if op.net_profit > 0:
            results.append(op)
    results.sort(key=lambda o: -o.net_profit)

    if not results:
        print("Nenhuma fresta com lucro líquido positivo agora. (O esperado — mas o")
        print("radar continua caçando janelas de volatilidade.)")
    else:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        for op in results[:10]:
            rota = " → ".join(op.path)
            vias = " / ".join(op.dexes)
            linha = (f"✅ {rota} [{vias}] | entrada ~{op.borrow:,.0f} {base} | "
                     f"líquido +{op.net_profit:.2f}")
            print(linha)
            if log_path:
                with open(log_path, "a", encoding="utf-8") as lf:
                    lf.write(f"{stamp} | {linha}\n")
    print("=" * 72)
    return len(results)
