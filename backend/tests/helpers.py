from __future__ import annotations

import random

from app.market.candle import Candle

T0 = 1_700_000_000


def seq(*ohlc: tuple[float, float, float, float], start_ts: int = T0, tf: int = 60) -> list[Candle]:
    """Monta velas a partir de tuplas (open, high, low, close)."""
    return [Candle(ts=start_ts + i * tf, open=o, high=h, low=lo, close=c) for i, (o, h, lo, c) in enumerate(ohlc)]


def random_walk(n: int, seed: int = 7, start: float = 1.1000, vol: float = 0.0005, drift_every: int = 60) -> list[Candle]:
    """Velas sintéticas determinísticas, com trechos de tendência e velas carecas às vezes."""
    rng = random.Random(seed)
    price = start
    out: list[Candle] = []
    drift = 0.0
    for i in range(n):
        if i % drift_every == 0:
            drift = rng.choice((-1, 0, 1)) * vol * 0.4
        o = price
        c = o + drift + rng.gauss(0, vol)
        up = rng.random() * vol * 0.8 if rng.random() > 0.3 else 0.0
        dn = rng.random() * vol * 0.8 if rng.random() > 0.3 else 0.0
        out.append(Candle(ts=T0 + 60 * i, open=o, high=max(o, c) + up, low=min(o, c) - dn, close=c))
        price = c
    return out
