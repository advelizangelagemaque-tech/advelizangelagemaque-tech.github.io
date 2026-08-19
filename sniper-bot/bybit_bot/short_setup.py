"""Detector de ROLLOVER (setup de short honesto, só leitura).

"Sobrecomprado" NÃO é sinal de short — é armadilha de squeeze. O short com a
matemática do seu lado é outro: esperar o pump MORRER e só então vender, com stop
curto acima da máxima. Este detector faz exatamente isso. Ele só acende a luz de
SHORT quando, TODAS juntas:

  1. a moeda esticou (subiu forte na janela recente)      -> tem o que cair;
  2. já recuou da máxima (pullback)                        -> o topo passou;
  3. o preço perdeu a média rápida                         -> tendência curta virou;
  4. o RSI saiu do topo (momentum enfraquecendo)           -> força acabando;
  5. mas ainda está elevada (não desabou tudo já)          -> não é short atrasado.

Se ainda está subindo/no topo, ele te SEGURA (🔴 não shortar) — que é onde a
maioria se liquida. NÃO opera; só lê e te dá o veredito e o stop sugerido.
"""

from __future__ import annotations

import argparse
import logging

from .entry_check import rsi, sma

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("bybit_bot.short_setup")


# ---- lógica pura (testável) ------------------------------------------------

def detect_short_setup(candles: list, fast: int = 7, mid: int = 21,
                       lookback: int = 20, pump_min: float = 0.25,
                       pullback_min: float = 0.10, base_lb: int = 60,
                       rsi_floor: float = 35.0, pullback_max: float = 0.35) -> dict:
    """Analisa candles [ts,o,h,l,c,v] e devolve o veredito de short."""
    highs = [c[2] for c in candles]
    closes = [c[4] for c in candles]
    price = closes[-1]
    window = closes[-lookback:] if len(closes) >= lookback else closes
    win_hi = max(window)
    win_lo = min(window)
    base_low = min(closes[-base_lb:]) if len(closes) >= base_lb else min(closes)  # base pré-pump
    recent_high = max(highs[-lookback:]) if len(highs) >= lookback else max(highs)

    ma_fast = sma(closes, fast)
    ma_mid = sma(closes, mid)
    r = rsi(closes, 14)

    # 1) esticou? subiu >= pump_min dentro da janela
    ran = (win_hi / win_lo - 1.0) if win_lo > 0 else 0.0
    pumped = ran >= pump_min
    # 2) recuou da máxima?
    pulled_back = price <= recent_high * (1.0 - pullback_min)
    # 3) perdeu a média rápida?
    below_fast = ma_fast is not None and price < ma_fast
    fast_below_mid = ma_fast is not None and ma_mid is not None and ma_fast < ma_mid
    # 4) momentum saindo do topo?
    momentum_down = r is not None and r < 55.0
    # 5) ainda elevada (não desabou tudo de volta pra base pré-pump)?
    still_elevated = base_low > 0 and price > base_low * (1.0 + 0.10)
    # 6) NÃO sobrevendido: se o RSI já está no fundo, o tombo já aconteceu ->
    #    shortar aqui é tarde (zona de repique). Escudo anti-fundo.
    not_oversold = r is not None and r > rsi_floor
    # 7) NÃO caiu demais: se já despencou > pullback_max do topo, o grosso da
    #    queda passou (AKE -40%, APR -75%) -> tarde pra short, risco de repique.
    not_too_deep = price >= recent_high * (1.0 - pullback_max)

    rolling = (pumped and pulled_back and below_fast and momentum_down
               and still_elevated and not_oversold and not_too_deep)

    if not pumped:
        verdict = "⚪ SEM SETUP — não esticou o bastante. Não é candidato a short."
        light = "none"
    elif rolling:
        verdict = "🟢 SHORT VÁLIDO — o pump virou pra baixo (rollover confirmado)."
        light = "short"
    else:
        verdict = ("🔴 NÃO SHORTAR — esticado, mas ainda de pé (subindo/no topo). "
                   "Aqui é onde o short apanha do squeeze. ESPERE virar.")
        light = "wait"

    dist_stop = (recent_high / price - 1.0) * 100 if price > 0 else 0.0
    return {"light": light, "verdict": verdict, "price": price, "rsi": round(r, 1) if r else None,
            "recent_high": recent_high, "ma_fast": ma_fast, "ma_mid": ma_mid,
            "pumped": pumped, "pulled_back": pulled_back, "below_fast": below_fast,
            "momentum_down": momentum_down, "still_elevated": still_elevated,
            "not_oversold": not_oversold, "not_too_deep": not_too_deep,
            "rolling": rolling, "dist_stop_pct": round(dist_stop, 1),
            "ran_pct": round(ran * 100, 1)}


# ---- coleta (rede pública, só leitura) -------------------------------------

def fetch_candles(symbol: str, tf: str = "4h", limit: int = 120) -> list:
    try:
        import ccxt
    except ImportError:
        raise SystemExit("ccxt não está instalado. Rode:  pip3 install ccxt")
    ex = ccxt.bybit({"enableRateLimit": True, "options": {"defaultType": "swap"}})
    return ex.fetch_ohlcv(symbol, tf, limit=limit)


def _check(v: bool) -> str:
    return "✅" if v else "—"


def run(symbol: str, tf: str) -> int:
    log.warning("Buscando candles de %s (%s)...", symbol, tf)
    candles = fetch_candles(symbol, tf)
    if len(candles) < 30:
        log.error("Pouco histórico pra %s.", symbol)
        return 1
    d = detect_short_setup(candles)
    print("=" * 66)
    print(f"DETECTOR DE ROLLOVER (short) — {symbol}  ({tf})")
    print("=" * 66)
    print(f"Preço agora : {d['price']:.6g}   |   RSI(14): {d['rsi']}")
    print(f"Máxima recente (stop sugerido acima dela): {d['recent_high']:.6g} "
          f"(+{d['dist_stop_pct']:.1f}% daqui)")
    print("-" * 66)
    print("Condições pro short (precisa de TODAS):")
    print(f"   {_check(d['pumped'])} esticou (subiu {d['ran_pct']:.0f}% na janela)")
    print(f"   {_check(d['pulled_back'])} já recuou da máxima")
    print(f"   {_check(d['below_fast'])} perdeu a média rápida")
    print(f"   {_check(d['momentum_down'])} RSI saiu do topo (<55)")
    print(f"   {_check(d['still_elevated'])} ainda elevada (não desabou tudo)")
    print(f"   {_check(d['not_oversold'])} não sobrevendida (RSI>35, o tombo ainda não passou)")
    print(f"   {_check(d['not_too_deep'])} não caiu demais (< 35% do topo, ainda dá pra pegar)")
    print("-" * 66)
    print(d["verdict"])
    if d["light"] == "short":
        print(f"👉 Se shortar: stop logo ACIMA de {d['recent_high']:.6g}, "
              f"valor pequeno, alavancagem baixa (2x).")
    print("=" * 66)
    print("LEMBRE: short tem risco INFINITO (a moeda pode dobrar). Só com stop e")
    print("pouco. 'Sobrecomprado' sozinho NUNCA é short — este detector existe pra")
    print("te impedir de vender na subida. Espere a luz 🟢.")
    print("=" * 66)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Detector de rollover / setup de short (só leitura).")
    p.add_argument("symbol", nargs="?", default="BTC/USDT:USDT", help="Token (ex: GWEI/USDT:USDT).")
    p.add_argument("--tf", default="4h", help="Timeframe (padrão 4h; use 1d pra mais confiável).")
    args = p.parse_args()
    return run(args.symbol, args.tf)


if __name__ == "__main__":
    import sys
    sys.exit(main())
