"""Gera uma carteira-isca (burner) para o sniper Solana.

Cria um novo par de chaves e salva no formato da Solana CLI (lista de bytes),
com permissão 600. NUNCA use sua carteira principal — esta é descartável e deve
conter apenas o valor que você pode perder.

Uso:
    python -m solana_sniper.gen_wallet                 # ~/.config/solana/burner.json
    python -m solana_sniper.gen_wallet --out burner.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys


def generate(path: str, force: bool = False) -> str:
    """Cria o keypair e o salva. Retorna o endereço público (pubkey)."""
    from solders.keypair import Keypair

    path = os.path.expanduser(path)
    if os.path.exists(path) and not force:
        raise FileExistsError(
            f"Já existe um arquivo em {path}. Use --force para sobrescrever "
            "(CUIDADO: isso descarta a carteira antiga)."
        )
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    kp = Keypair()
    secret = list(bytes(kp))  # 64 bytes no formato da Solana CLI
    with open(path, "w", encoding="utf-8") as f:
        json.dump(secret, f)
    os.chmod(path, 0o600)
    return str(kp.pubkey())


def main() -> int:
    ap = argparse.ArgumentParser(description="Gera carteira-isca (burner) Solana")
    ap.add_argument("--out", default="~/.config/solana/burner.json")
    ap.add_argument("--force", action="store_true", help="Sobrescreve se já existir.")
    args = ap.parse_args()
    try:
        pubkey = generate(args.out, args.force)
    except FileExistsError as exc:
        print(exc)
        return 1
    print("Carteira-isca criada com sucesso! 🔑")
    print(f"  Arquivo : {os.path.expanduser(args.out)}  (permissão 600)")
    print(f"  Endereço: {pubkey}")
    print()
    print(">> DEPOSITE aqui APENAS o valor que pode perder (ex.: 0.05 SOL).")
    print(">> Nunca use sua carteira principal. Esta é descartável.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
