"""CLI do simulador de flash loan (Fase 0). Sempre só observa — nunca opera."""

from __future__ import annotations

import argparse


def main() -> int:
    p = argparse.ArgumentParser(
        description="Simulador de arbitragem com flash loan (Fase 0: só mede, não opera).")
    p.add_argument("--demo", action="store_true",
                   help="Roda cenários de exemplo na hora (sem internet, sem risco).")
    p.add_argument("--scan", metavar="CONFIG.json",
                   help="Lê preços REAIS e mede arbitragem de 2 pontas (mesmo par, 2 DEXs).")
    p.add_argument("--tri", metavar="CONFIG.json",
                   help="CAÇA À FRESTA: arbitragem triangular/em ciclo entre vários tokens.")
    p.add_argument("--watch", type=float, default=0, metavar="SEG",
                   help="RADAR: repete a leitura a cada SEG segundos (ex: --watch 60).")
    p.add_argument("--log", metavar="ARQ.txt",
                   help="Anota as frestas positivas neste arquivo (com data/hora).")
    p.add_argument("--list-chains", action="store_true",
                   help="Lista as redes baratas suportadas e o gás estimado.")
    args = p.parse_args()

    if args.list_chains:
        from .chains import CHAINS
        print("Redes suportadas (gás estimado por arbitragem):")
        for c in CHAINS.values():
            print(f"  {c.key:9s} {c.name:14s} gás~${c.gas_usd:<6} flash {c.flash_fee_bps/100:.2f}%")
        return 0

    # escolhe o que rodar
    if args.tri:
        from .scan import scan_triangular
        run = lambda: scan_triangular(args.tri, log_path=args.log)  # noqa: E731
    elif args.scan:
        from .scan import scan
        run = lambda: scan(args.scan)  # noqa: E731
    else:
        from .demo import run_demo
        return run_demo()

    if args.watch and args.watch > 0:
        import time
        print(f"RADAR ligado: relendo a cada {args.watch:.0f}s. Ctrl+C para parar.\n")
        while True:
            try:
                run()
            except SystemExit:
                raise
            except Exception as exc:  # noqa: BLE001
                print(f"(erro nesta rodada, sigo tentando: {str(exc)[:80]})")
            time.sleep(args.watch)
    return run()


if __name__ == "__main__":
    import sys
    sys.exit(main())
