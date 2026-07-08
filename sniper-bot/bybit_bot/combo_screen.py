"""Rastreador de carteira pro FUTURES COMBO da Bybit (só leitura, sem chave).

O Combo é uma carteira long/short rebalanceada — a versão NATIVA do nosso Delta.
A pergunta é: quais moedas pôr, e de que lado? Aqui a gente escolhe pelo FUNDING:
- moedas com funding MUITO POSITIVO -> a gente fica SHORT (recebe o funding);
- moedas com funding NEGATIVO/baixo -> a gente fica LONG (recebe, ou paga pouco).
Assim a carteira fica ~neutra de mercado E colhe o carrego (funding) dos dois lados.

Também mostra volume (liquidez) e volatilidade 24h, pra você fugir de moeda fina
que explode. Isto NÃO opera — só te dá a lista pra montar o Combo na mão, na Bybit.
"""

from __future__ import annotations

import argparse
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("bybit_bot.combo_screen")


# ---- lógica pura (testável) ------------------------------------------------

def funding_rows(tickers: dict, min_vol_usdt: float) -> list[dict]:
    """Perps USDT líquidos com funding: [{symbol, funding, vol, vol24h}]."""
    rows = []
    for sym, t in tickers.items():
        if not sym.endswith(":USDT"):
            continue
        vol = t.get("quoteVolume") or t.get("baseVolume")
        if vol is None or float(vol) < min_vol_usdt:
            continue
        info = t.get("info") or {}
        fr = info.get("fundingRate")
        if fr in (None, ""):
            continue
        # volatilidade 24h: |variação%| do dia (proxy simples de "quanto ela mexe")
        pct = t.get("percentage")
        vol24 = abs(float(pct)) if pct is not None else 0.0
        rows.append({"symbol": sym, "funding": float(fr), "vol": float(vol),
                     "vol24h": vol24})
    return rows


def annualized(funding_8h: float) -> float:
    """Funding é cobrado a cada 8h (3x/dia). Anualiza pra ficar palpável."""
    return funding_8h * 3 * 365


def build_combo(rows: list[dict], k: int, max_vol24h: float = 25.0) -> dict:
    """Monta a carteira: k SHORTs (funding mais positivo) + k LONGs (mais negativo).
    Descarta moedas muito voláteis (>max_vol24h% no dia) — perigosas num combo.
    Pesos iguais dos dois lados (neutro). Devolve dict pronto pra montar na Bybit."""
    liquid = [r for r in rows if r["vol24h"] <= max_vol24h]
    s = sorted(liquid, key=lambda r: r["funding"])           # do mais negativo ao mais positivo
    if len(s) < 2 * k:
        k = len(s) // 2
    if k <= 0:
        return {"longs": [], "shorts": [], "carry_anual_pct": 0.0}
    longs = s[:k]                                            # funding baixo/negativo -> LONG recebe
    shorts = s[-k:]                                          # funding alto -> SHORT recebe
    longset = {r["symbol"] for r in longs}
    shorts = [r for r in shorts if r["symbol"] not in longset]
    weight = round(100.0 / (len(longs) + len(shorts)), 1)
    # carrego anual estimado: SHORT recebe +funding, LONG recebe -funding
    carry_8h = sum(r["funding"] for r in shorts) - sum(r["funding"] for r in longs)
    n = len(longs) + len(shorts)
    carry_anual = annualized(carry_8h / n) * 100 if n else 0.0
    return {"longs": longs, "shorts": shorts, "weight_pct": weight,
            "carry_anual_pct": carry_anual}


# ---- coleta (rede pública, só leitura) -------------------------------------

def fetch_tickers() -> dict:
    try:
        import ccxt
    except ImportError:
        raise SystemExit("ccxt não está instalado. Rode:  pip3 install ccxt")
    ex = ccxt.bybit({"enableRateLimit": True, "options": {"defaultType": "swap"}})
    return ex.fetch_tickers()


def run(min_vol: float, k: int, max_vol24h: float) -> int:
    log.warning("Buscando funding de todos os perps USDT da Bybit...")
    tickers = fetch_tickers()
    rows = funding_rows(tickers, min_vol)
    if not rows:
        log.error("Sem dados de funding. Verifique a conexão/ccxt.")
        return 1
    combo = build_combo(rows, k, max_vol24h)
    print("=" * 70)
    print(f"CARTEIRA COMBO (funding) | {len(rows)} moedas líquidas | vol.min ${min_vol/1e6:.0f}M")
    print(f"Regra: SHORT quem paga funding alto, LONG quem paga baixo/negativo.")
    print(f"Descartadas as que mexem mais de {max_vol24h:.0f}% no dia (voláteis demais).")
    print("=" * 70)
    print("\n🔻 SHORT (a carteira RECEBE o funding alto):")
    for r in reversed(combo["shorts"]):
        print(f"    {r['symbol']:<22} funding {r['funding']*100:+.4f}%/8h "
              f"(~{annualized(r['funding'])*100:+.0f}%/ano)  vol24h {r['vol24h']:.1f}%")
    print("\n🟢 LONG (funding baixo/negativo — a carteira recebe ou paga pouco):")
    for r in combo["longs"]:
        print(f"    {r['symbol']:<22} funding {r['funding']*100:+.4f}%/8h "
              f"(~{annualized(r['funding'])*100:+.0f}%/ano)  vol24h {r['vol24h']:.1f}%")
    print("\n" + "-" * 70)
    print(f"Peso sugerido: {combo['weight_pct']:.1f}% em cada perna ({len(combo['longs'])}"
          f" long + {len(combo['shorts'])} short = neutro).")
    print(f"Carrego (funding) estimado da carteira: ~{combo['carry_anual_pct']:+.1f}%/ano")
    print("=" * 70)
    print("HONESTIDADE: funding MUDA o tempo todo (a cada 8h) — esta lista é de AGORA,")
    print("não de sempre. O carrego é o 'extra'; o resultado final também depende de")
    print("preço. Combo com alavancagem 1x-2x e rebalance. Reveja a lista toda semana.")
    print("=" * 70)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description="Rastreador de carteira pro Futures Combo da Bybit (funding, só leitura).")
    p.add_argument("--min-vol", type=float, default=30_000_000,
                   help="Volume 24h mínimo em USDT (padrão 30M = só moedas líquidas).")
    p.add_argument("--k", type=int, default=3, help="Moedas por lado (padrão 3 long + 3 short).")
    p.add_argument("--max-vol24h", type=float, default=25.0,
                   help="Descarta moedas que mexem mais que isso no dia, em %% (padrão 25).")
    args = p.parse_args()
    return run(args.min_vol, args.k, args.max_vol24h)


if __name__ == "__main__":
    import sys
    sys.exit(main())
