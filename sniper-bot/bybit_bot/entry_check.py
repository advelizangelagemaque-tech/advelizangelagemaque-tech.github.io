"""Medidor de ENTRADA (só leitura): transforma "será que compro?" em REGRA.

Ninguém acerta o fundo. Mas dá pra fugir do erro caro — comprar topo esticado —
e favorecer a compra no desconto. Este medidor puxa o diário de um token e devolve
uma nota objetiva de 0 a 100 (quanto MAIOR, melhor a zona de compra), combinando:

  • RSI(14) diário  -> sobrevendido (baixo) = desconto; sobrecomprado (>70) = espere;
  • posição na faixa -> preço perto da MÍNIMA recente = barato; perto da máxima = caro;
  • tendência (MM50) -> só um aviso de contexto (a favor ou contra a maré grande).

NÃO prevê o futuro e NÃO opera. Ele impõe DISCIPLINA. Regra de ouro embaixo: compre
em PARTES (DCA), nunca tudo de uma vez — assim você não depende de acertar o momento.
"""

from __future__ import annotations

import argparse
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("bybit_bot.entry_check")


# ---- matemática pura (testável) --------------------------------------------

def sma(closes: list, n: int) -> float | None:
    """Média móvel simples dos últimos n fechamentos."""
    if len(closes) < n or n <= 0:
        return None
    return sum(closes[-n:]) / n


def rsi(closes: list, n: int = 14) -> float | None:
    """RSI de Wilder. 0-100. >70 sobrecomprado, <30 sobrevendido."""
    if len(closes) < n + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_gain = sum(gains[:n]) / n
    avg_loss = sum(losses[:n]) / n
    for i in range(n, len(gains)):                       # suavização de Wilder
        avg_gain = (avg_gain * (n - 1) + gains[i]) / n
        avg_loss = (avg_loss * (n - 1) + losses[i]) / n
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def rsi_series(closes: list, n: int = 14) -> list:
    """Série de RSI (Wilder), um valor por ponto a partir do índice n."""
    if len(closes) < n + 1:
        return []
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_gain = sum(gains[:n]) / n
    avg_loss = sum(losses[:n]) / n

    def _val(ag, al):
        if al == 0:
            return 100.0
        return 100.0 - 100.0 / (1.0 + ag / al)

    out = [_val(avg_gain, avg_loss)]
    for i in range(n, len(gains)):
        avg_gain = (avg_gain * (n - 1) + gains[i]) / n
        avg_loss = (avg_loss * (n - 1) + losses[i]) / n
        out.append(_val(avg_gain, avg_loss))
    return out


def stoch_rsi(closes: list, rsi_n: int = 14, stoch_n: int = 14, k: int = 3) -> float | None:
    """Stoch RSI %K (0-100). Onde o RSI está na faixa dele. Baixo (<20) =
    sobrevendido de curto prazo (o tombo já passou, risco de repique)."""
    rs = rsi_series(closes, rsi_n)
    if len(rs) < stoch_n:
        return None
    raw = []
    for i in range(stoch_n - 1, len(rs)):
        w = rs[i - stoch_n + 1:i + 1]
        lo, hi = min(w), max(w)
        raw.append(50.0 if hi == lo else (rs[i] - lo) / (hi - lo) * 100.0)
    if not raw:
        return None
    kk = raw[-k:] if len(raw) >= k else raw            # %K = média dos últimos k
    return sum(kk) / len(kk)


def range_position(closes: list, lookback: int = 90) -> float:
    """Onde o preço está entre a mínima (0.0) e a máxima (1.0) da janela recente."""
    w = closes[-lookback:] if len(closes) >= lookback else closes
    lo, hi = min(w), max(w)
    if hi == lo:
        return 0.5
    return (closes[-1] - lo) / (hi - lo)


def _clamp(x: float, a: float = 0.0, b: float = 100.0) -> float:
    return max(a, min(b, x))


def entry_score(closes: list, lookback: int = 90) -> dict:
    """Nota 0-100 de zona de compra (maior = melhor) + veredito honesto.

    REGRA DURA: RSI>=70 sempre vira 'ESPERE' (não se compra topo esticado),
    por mais tentador que o gráfico esteja."""
    r = rsi(closes, 14)
    pos = range_position(closes, lookback)
    ma50 = sma(closes, 50)
    price = closes[-1]
    trend_up = ma50 is not None and price >= ma50
    if r is None:
        return {"score": None, "rsi": None, "pos": pos, "trend_up": trend_up,
                "verdict": "sem dados suficientes"}
    rsi_score = _clamp((70.0 - r) / 40.0 * 100.0)        # rsi 30->100, 70->0
    range_score = (1.0 - pos) * 100.0                    # perto da mínima -> alto
    score = round(0.5 * rsi_score + 0.5 * range_score, 1)
    if r >= 70:
        verdict = "🔴 ESPERE — esticado (sobrecomprado). Comprar aqui é caçar topo."
    elif score >= 65:
        verdict = "🟢 BOA ZONA — preço com desconto/fraqueza. Compre em partes."
    elif score >= 40:
        verdict = "🟡 NEUTRO — sem desconto claro. Se comprar, em partes (DCA)."
    else:
        verdict = "🟠 CARO na faixa — espere um recuo, ou só um DCA pequeno."
    return {"score": score, "rsi": round(r, 1), "pos": round(pos, 2),
            "trend_up": trend_up, "verdict": verdict}


# ---- coleta (rede pública, só leitura) -------------------------------------

def fetch_closes(symbol: str, days: int = 180) -> list:
    try:
        import ccxt
    except ImportError:
        raise SystemExit("ccxt não está instalado. Rode:  pip3 install ccxt")
    ex = ccxt.bybit({"enableRateLimit": True, "options": {"defaultType": "swap"}})
    ohlcv = ex.fetch_ohlcv(symbol, "1d", limit=days)
    return [c[4] for c in ohlcv]


def run(symbol: str, days: int, lookback: int) -> int:
    log.warning("Buscando %d dias de %s (diário)...", days, symbol)
    closes = fetch_closes(symbol, days)
    if len(closes) < 60:
        log.error("Pouco histórico pra %s.", symbol)
        return 1
    e = entry_score(closes, lookback)
    price = closes[-1]
    print("=" * 66)
    print(f"MEDIDOR DE ENTRADA — {symbol}  (diário, {len(closes)} dias)")
    print("=" * 66)
    print(f"Preço agora     : {price:.6g}")
    print(f"RSI(14) diário  : {e['rsi']}  "
          f"({'sobrecomprado' if e['rsi'] >= 70 else 'sobrevendido' if e['rsi'] <= 30 else 'neutro'})")
    print(f"Posição na faixa: {e['pos']*100:.0f}%  (0% = mínima / 100% = máxima dos {lookback}d)")
    print(f"Tendência (MM50): {'a favor (acima da média)' if e['trend_up'] else 'contra (abaixo da média)'}")
    print(f"NOTA de compra  : {e['score']}/100")
    print("-" * 66)
    print(e["verdict"])
    print("=" * 66)
    print("REGRA DE OURO: compre em 3-4 PARTES (DCA), em dias/semanas diferentes —")
    print("assim você não precisa acertar o fundo. Nota alta = compre uma parte maior;")
    print("nota baixa = espere ou compre uma parte pequena. Isto é DISCIPLINA, não bola")
    print("de cristal: nada aqui prevê o futuro, só te tira do erro de comprar topo.")
    print("=" * 66)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Medidor de entrada (diário, só leitura).")
    p.add_argument("symbol", nargs="?", default="BTC/USDT:USDT",
                   help="Token (ex: BTC/USDT:USDT). Padrão BTC.")
    p.add_argument("--days", type=int, default=180, help="Dias de histórico (padrão 180).")
    p.add_argument("--lookback", type=int, default=90,
                   help="Janela da faixa mín/máx, em dias (padrão 90).")
    args = p.parse_args()
    return run(args.symbol, args.days, args.lookback)


if __name__ == "__main__":
    import sys
    sys.exit(main())
