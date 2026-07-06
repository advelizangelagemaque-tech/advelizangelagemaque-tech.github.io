"""CLI do simulador de flash loan (Fase 0). Sempre só observa — nunca opera."""

from __future__ import annotations

import argparse


def main() -> int:
    p = argparse.ArgumentParser(
        description="Simulador de arbitragem com flash loan (Fase 0: só mede, não opera).")
    p.add_argument("--demo", action="store_true",
                   help="Roda cenários de exemplo na hora (sem internet, sem risco).")
    p.add_argument("--scan", metavar="CONFIG.json",
                   help="Lê preços REAIS das DEXs a partir de um arquivo de config.")
    p.add_argument("--list-chains", action="store_true",
                   help="Lista as redes baratas suportadas e o gás estimado.")
    args = p.parse_args()

    if args.list_chains:
        from .chains import CHAINS
        print("Redes suportadas (gás estimado por arbitragem):")
        for c in CHAINS.values():
            print(f"  {c.key:9s} {c.name:14s} gás~${c.gas_usd:<6} flash {c.flash_fee_bps/100:.2f}%")
        return 0
    if args.scan:
        from .scan import scan
        return scan(args.scan)
    # padrão: demonstração (o jeito seguro de começar)
    from .demo import run_demo
    return run_demo()


if __name__ == "__main__":
    import sys
    sys.exit(main())
