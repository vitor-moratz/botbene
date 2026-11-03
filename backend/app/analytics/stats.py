"""Estatísticas de acerto com intervalo de confiança.

Taxa de acerto = vitórias / (vitórias + perdas); empates ficam de fora (a IQ devolve a entrada).
O intervalo de Wilson (95%) mostra o quanto o número ainda pode variar: com poucas entradas
ele é largo, e só quando o limite INFERIOR passa do mínimo para empatar dá para confiar.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass

from app.paper import DRAW, LOSS, WIN


def breakeven(payout: float) -> float:
    """Acerto mínimo para não perder dinheiro: 1 / (1 + payout)."""
    return 1.0 / (1.0 + payout)


def wilson(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p = wins / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, center - half), min(1.0, center + half)


@dataclass
class Group:
    key: str
    n: int = 0  # vitórias + perdas
    wins: int = 0
    losses: int = 0
    draws: int = 0
    profit: float = 0.0  # em entradas de 1 unidade
    payout_sum: float = 0.0
    winrate: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    breakeven: float | None = None

    def add(self, result: str, profit: float, payout: float) -> None:
        if result == WIN:
            self.wins += 1
        elif result == LOSS:
            self.losses += 1
        elif result == DRAW:
            self.draws += 1
        else:
            return
        self.profit += profit
        self.payout_sum += payout

    def finish(self) -> Group:
        self.n = self.wins + self.losses
        total = self.n + self.draws
        if total:
            self.breakeven = breakeven(self.payout_sum / total)
        if self.n:
            self.winrate = self.wins / self.n
            self.ci_low, self.ci_high = wilson(self.wins, self.n)
        self.profit = round(self.profit, 4)
        return self

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("payout_sum")
        return d


def summarize(rows: Iterable[dict], key: Callable[[dict], str]) -> list[Group]:
    groups: dict[str, Group] = defaultdict(lambda: Group(key=""))
    for row in rows:
        k = key(row)
        g = groups[k]
        g.key = k
        g.add(row["result"], row.get("profit") or 0.0, row.get("payout") or 0.0)
    return [g.finish() for g in groups.values()]


def total(rows: Iterable[dict]) -> Group:
    found = summarize(rows, lambda _: "total")
    return found[0] if found else Group(key="total").finish()
