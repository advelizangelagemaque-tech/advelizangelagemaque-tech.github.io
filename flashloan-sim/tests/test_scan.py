"""Testes da parte pura do scanner (orientação das reservas). O acesso à rede
não é testado aqui — é só leitura on-chain e depende de RPC."""

from flashsim.scan import orient_reserves

USDC = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
WMATIC = "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270"


def test_orient_quando_usdc_e_token0():
    # token0 == USDC: r0 é USDC (6 casas), r1 é o token (18 casas)
    usdc, tok = orient_reserves(USDC, USDC, r0=5_000_000_000, r1=3_000_000 * 10**18,
                                usdc_dec=6, token_dec=18)
    assert usdc == 5000.0
    assert tok == 3_000_000.0


def test_orient_quando_usdc_e_token1():
    # token0 == WMATIC: agora r0 é o token e r1 é o USDC
    usdc, tok = orient_reserves(WMATIC, USDC, r0=3_000_000 * 10**18, r1=5_000_000_000,
                                usdc_dec=6, token_dec=18)
    assert usdc == 5000.0
    assert tok == 3_000_000.0


def test_orient_ignora_maiuscula_minuscula():
    usdc, _ = orient_reserves(USDC.lower(), USDC.upper(), r0=1_000_000, r1=1,
                              usdc_dec=6, token_dec=18)
    assert usdc == 1.0
