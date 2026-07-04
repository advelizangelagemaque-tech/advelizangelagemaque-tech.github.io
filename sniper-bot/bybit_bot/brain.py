"""O 'cérebro' do agente: gestão de risco automática com base no resultado real.

Filosofia (aprendida na dor, com dados reais): NÃO tentamos prever qual token
vai subir — provou-se que esses sinais invertem (ruído). O cérebro ajusta o
RISCO conforme o desempenho recente:

  - perdendo (PF < 1 ou expectativa negativa)  -> reduz a margem pela metade;
  - sequência ruim (N perdas seguidas) ou PF muito baixo -> PAUSA novas entradas;
  - rombo grande no saldo (drawdown)            -> PAUSA (disjuntor);
  - voltou a ir bem                             -> volta ao normal sozinho.

Ele reavalia a cada ciclo, então retoma automaticamente quando melhora.
"""

from __future__ import annotations


# ---- métricas puras (testáveis) --------------------------------------------

def rolling_pf(pnls: list[float]) -> float:
    """Profit factor de uma janela de trades (ganhos / perdas)."""
    wins = sum(p for p in pnls if p > 0)
    losses = -sum(p for p in pnls if p < 0)
    if losses == 0:
        return float("inf") if wins > 0 else 1.0
    return wins / losses


def consec_losses(pnls: list[float]) -> int:
    """Perdas consecutivas mais recentes (no fim da lista)."""
    n = 0
    for p in reversed(pnls):
        if p < 0:
            n += 1
        else:
            break
    return n


def decide(recent_pnls: list[float], cfg) -> dict:
    """Decide exposição a partir do desempenho recente.

    Retorna {open_allowed, margin_mult, reason}. margin_mult multiplica a margem
    por trade (1.0 = normal, 0.5 = metade, 0.0 = não abre).
    """
    n = len(recent_pnls)
    if n < cfg.brain_min_trades:
        return {"open_allowed": True, "margin_mult": 1.0,
                "reason": f"aprendendo ({n}/{cfg.brain_min_trades} trades)"}
    pf = rolling_pf(recent_pnls)
    cl = consec_losses(recent_pnls)
    exp = sum(recent_pnls) / n

    if cl >= cfg.brain_pause_streak or pf < cfg.brain_pause_pf:
        return {"open_allowed": False, "margin_mult": 0.0,
                "reason": f"PAUSA defensiva (PF {pf:.2f}, {cl} perdas seguidas)"}
    if pf < cfg.brain_reduce_pf or exp < 0:
        return {"open_allowed": True, "margin_mult": 0.5,
                "reason": f"risco reduzido à metade (PF {pf:.2f})"}
    return {"open_allowed": True, "margin_mult": 1.0, "reason": f"normal (PF {pf:.2f})"}


def drawdown_ok(balance: float, peak: float, max_dd: float) -> bool:
    """False se o saldo caiu mais que max_dd (fração) do topo — aciona o disjuntor."""
    if peak <= 0:
        return True
    return balance >= peak * (1.0 - max_dd)


def exposure_for_drawdown(dd: float, warn_dd: float, hard_dd: float) -> dict:
    """Cérebro do Delta: define a exposição pela queda do saldo (drawdown).

    dd = quanto o saldo caiu do topo (fração, 0.08 = -8%).
    Retorna {mult, flatten, reason}: mult multiplica a exposição bruta; flatten=True
    manda ficar em CAIXA (fecha tudo) no disjuntor.
    """
    if dd >= hard_dd:
        return {"mult": 0.0, "flatten": True,
                "reason": f"disjuntor: saldo -{dd * 100:.1f}% do topo — em caixa"}
    if dd >= warn_dd:
        return {"mult": 0.5, "flatten": False,
                "reason": f"risco reduzido à metade (saldo -{dd * 100:.1f}%)"}
    return {"mult": 1.0, "flatten": False, "reason": "normal"}
