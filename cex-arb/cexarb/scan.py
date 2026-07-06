"""Medidor de gap entre corretoras (CEX-CEX). Só LEITURA: lê os livros de ordem
públicos das duas corretoras (sem chave, sem login) e mede o lucro REAL possível.
"""

from __future__ import annotations

from .gap import Book, compute_gap

# taxas de taker padrão (spot). Ajuste se a sua conta tiver taxa diferente.
DEFAULT_FEES = {"bybit": 0.001, "binance": 0.001, "okx": 0.001}

DEFAULT_PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "DOGE/USDT"]


def _make(name: str):
    import ccxt
    cls = getattr(ccxt, name, None)
    if cls is None:
        raise SystemExit(f"Corretora desconhecida no ccxt: {name}")
    return cls({"enableRateLimit": True, "options": {"defaultType": "spot"}})


def _book(ex, name: str, symbol: str) -> Book | None:
    try:
        ob = ex.fetch_order_book(symbol, limit=5)
        bid = ob["bids"][0][0] if ob["bids"] else None
        ask = ob["asks"][0][0] if ob["asks"] else None
        if not bid or not ask:
            return None
        return Book(exchange=name, bid=float(bid), ask=float(ask))
    except Exception as exc:  # noqa: BLE001
        print(f"    ({name} falhou em {symbol}: {str(exc)[:70]})")
        return None


def scan(ex_a: str = "bybit", ex_b: str = "binance", pairs=None,
         fee_a: float | None = None, fee_b: float | None = None) -> int:
    try:
        import ccxt  # noqa: F401
    except ImportError:
        raise SystemExit("ccxt não está instalado. Rode:  pip install ccxt")

    pairs = pairs or DEFAULT_PAIRS
    fee_a = DEFAULT_FEES.get(ex_a, 0.001) if fee_a is None else fee_a
    fee_b = DEFAULT_FEES.get(ex_b, 0.001) if fee_b is None else fee_b

    try:
        a = _make(ex_a)
        b = _make(ex_b)
    except SystemExit:
        raise
    print("=" * 72)
    print(f"MEDINDO GAP {ex_a.upper()} x {ex_b.upper()} (spot, só leitura) | "
          f"taxa {fee_a*100:.3f}% + {fee_b*100:.3f}% por operação")
    print("=" * 72)
    print(f"{'par':12s} {'vitrine':>9s} {'real(líq)':>10s} {'por 1k USDT':>12s}  rota")
    print("-" * 72)

    achou = 0
    for sym in pairs:
        ba = _book(a, ex_a, sym)
        bb = _book(b, ex_b, sym)
        if ba is None or bb is None:
            continue
        g = compute_gap(sym, ba, bb, fee_a, fee_b)
        marca = "✅" if g.profitable else "—"
        rota = f"compra {g.buy_ex}→vende {g.sell_ex}" if g.profitable else ""
        print(f"{sym:12s} {g.displayed_gap_pct:>8.3f}% {g.net_pct:>9.3f}% "
              f"{g.net_usd_per_1k:>+11.2f}  {marca} {rota}")
        if g.profitable:
            achou += 1

    print("-" * 72)
    print(f"Pares com lucro REAL (depois das taxas) agora: {achou}")
    print("Repare: a coluna 'vitrine' quase sempre é bem maior que a 'real(líq)' —")
    print("é aí que muita gente se ilude. Só a coluna real conta. E mesmo positiva,")
    print("os bots fecham o gap em milissegundos. Isto é medição, não promessa.")
    print("=" * 72)
    return 0
