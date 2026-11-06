"""Placar de validação: a estratégia principal está provando vantagem AO VIVO?

Critério combinado (docs/estrategia.md): pelo menos 200 entradas ao vivo, com o limite inferior
da faixa de confiança (Wilson, 95%) acima do mínimo para empatar. Na prática, ~61% em 200
entradas ou ~59% em 500. Antes disso, qualquer acerto é só oscilação.
"""

from __future__ import annotations

import time
from collections.abc import Iterable

from app.analytics.stats import breakeven, total, wilson

TARGETS = (200, 500)
MIN_FOR_READING = 30  # abaixo disso os números ainda oscilam demais para dizer qualquer coisa


def needed_winrate(n: int, be: float) -> float | None:
    """Menor acerto que, com n entradas, deixa o pior caso da faixa acima do empate."""
    for wins in range(n + 1):
        if wilson(wins, n)[0] > be:
            return wins / n
    return None


def verdict(n: int, wins: int, be: float) -> dict:
    target = next((t for t in TARGETS if n < t), TARGETS[-1])
    low, high = wilson(wins, n)
    if n < MIN_FOR_READING:
        return {"code": "comecando", "title": "Começando",
                "detail": f"Com menos de {MIN_FOR_READING} entradas o acerto ainda oscila muito. Deixe o bot juntando."}
    if n >= TARGETS[0] and low > be:
        return {"code": "vantagem", "title": "Vantagem comprovada",
                "detail": "Mesmo no pior caso da faixa, o acerto fica acima do empate."}
    if n >= TARGETS[0] and high < be:
        return {"code": "abaixo", "title": "Abaixo do empate",
                "detail": "Mesmo no melhor caso da faixa, o acerto fica abaixo do empate: a estratégia está perdendo."}
    if n >= TARGETS[-1]:
        return {"code": "sem_vantagem", "title": "Sem vantagem",
                "detail": f"Depois de {n} entradas o acerto continua no empate: se existe vantagem, ela é pequena demais."}
    if n >= TARGETS[0]:
        return {"code": "empate", "title": "Ainda no empate",
                "detail": f"A faixa ainda cruza o empate. Próxima meta: {target} entradas."}
    return {"code": "juntando", "title": "Juntando amostra",
            "detail": f"Faltam {target - n} entradas para a primeira leitura confiável ({target})."}


def summarize_validation(name: str, label: str, signals: list[dict], orders: Iterable[dict],
                         default_payout: float, now: float | None = None) -> dict:
    """Números da estratégia `name` a partir dos sinais ao vivo resolvidos e das ordens enviadas."""
    now = time.time() if now is None else now
    g = total(signals)
    be = g.breakeven if g.breakeven is not None else breakeven(default_payout)
    target = next((t for t in TARGETS if g.n < t), TARGETS[-1])
    first_ts = min((s["entry_ts"] for s in signals), default=None)
    days = (now - first_ts) / 86400 if first_ts is not None else 0.0
    per_day = g.n / days if days >= 1 else None
    eta_days = (target - g.n) / per_day if per_day and g.n < target else None

    sent = [o for o in orders if o.get("strategy") == name]
    by_status: dict[str, int] = {}
    for o in sent:
        by_status[o["status"]] = by_status.get(o["status"], 0) + 1
    profit = round(sum(o.get("profit") or 0.0 for o in sent if o["status"] in ("win", "loss", "empate", "sem_resultado")), 2)

    return {
        "strategy": name, "label": label,
        "n": g.n, "wins": g.wins, "losses": g.losses, "draws": g.draws,
        "winrate": g.winrate, "ci_low": g.ci_low, "ci_high": g.ci_high,
        "breakeven": be, "target": target, "targets": list(TARGETS),
        "needed": {str(t): needed_winrate(t, be) for t in TARGETS},
        "profit_units": g.profit,
        "first_ts": first_ts, "per_day": per_day, "eta_days": eta_days,
        "verdict": verdict(g.n, g.wins, be),
        "orders": {"count": len(sent), "by_status": by_status, "profit": profit},
    }
