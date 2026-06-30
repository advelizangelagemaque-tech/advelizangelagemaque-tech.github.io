"""Cotação (read-only) e execução de swap (desativada por segurança).

`get_quote` consulta a API pública do Jupiter — somente leitura, não move
fundos. `execute_swap` está propositalmente desativada até validação em devnet.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

JUPITER_QUOTE = "https://quote-api.jup.ag/v6/quote"


def get_quote(input_mint: str, output_mint: str, amount: int,
              slippage_bps: int = 100, timeout: int = 10) -> dict:
    """Cotação de swap (read-only). `amount` em unidades mínimas do input_mint."""
    qs = urllib.parse.urlencode({
        "inputMint": input_mint, "outputMint": output_mint,
        "amount": amount, "slippageBps": slippage_bps,
    })
    with urllib.request.urlopen(f"{JUPITER_QUOTE}?{qs}", timeout=timeout) as resp:
        return json.loads(resp.read())


def execute_swap(*args, **kwargs):
    """DESATIVADO. Mover fundos exige assinatura (solders) e teste em devnet."""
    raise NotImplementedError(
        "execute_swap está desativada por segurança. Antes de ligar: "
        "(1) rode safety.check_token_safety; (2) use carteira-isca em devnet; "
        "(3) implemente a assinatura com solders e teste em devnet. Ver README."
    )
