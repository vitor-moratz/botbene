"""Confluências da Bollinger + RCI (09/11/2026): Gator, MACD, Weis Wave e Fractal, sobre as velas fechadas até k.

A v1 só anota estas marcações em cada sinal (não decide nada com elas). A v2 (bb_rci_v2.py) entra quando a v1
entra e as confluências exigidas estão a favor. Cada função devolve True (a favor), False (contra) ou None (sem
dados: aquecendo, ou Weis Wave sem volume, como no OTC da IQ, que manda volume zero).

- Gator (Bill Williams): Alligator com médias de Wilder da mediana (máxima+mínima)/2, de 13, 8 e 5 velas, deslocadas
  8, 5 e 3 velas para frente. Barra de cima = |mandíbula - dentes|, de baixo = |dentes - lábios|. "Dormindo" = as duas
  barras vermelhas na vela k (as duas distâncias diminuíram): mercado sem tendência acelerando.
- MACD 12/26/9: o histograma está contra a entrada, mas virando a favor (CALL: negativo e maior que o da vela anterior;
  PUT: positivo e menor). A força do movimento está cansando.
- Weis Wave: ondas de fechamento com virada mínima de 0,5 ATR; soma o volume de cada onda. A favor = a onda mais recente
  na direção do movimento que a entrada contraria tem MENOS volume que a onda anterior nessa mesma direção.
- Fractal (5 velas, só os já confirmados): o toque da vela k fica a até 0,5 ATR do último fractal na direção (CALL: de
  baixa; PUT: de alta) nas 30 velas anteriores.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.indicators.core import ema, rma
from app.market.candle import Candle
from app.strategies.base import Direction

LOOK = 160  # velas usadas no cálculo (aquecimento das médias com folga)


@dataclass(frozen=True)
class ConfluenceConfig:
    wave_atr: float = 0.5
    fractal_atr: float = 0.5
    fractal_lookback: int = 30
    atr_period: int = 14


def _atr(candles: Sequence[Candle], end: int, n: int) -> float:
    lo = max(0, end - n + 1)
    window = candles[lo:end + 1]
    return sum(c.high - c.low for c in window) / len(window) if window else 0.0


def gator_sleeping(candles: Sequence[Candle]) -> bool | None:
    med = [(c.high + c.low) / 2 for c in candles]
    jaw, teeth, lips = rma(med, 13), rma(med, 8), rma(med, 5)

    def bars(i: int) -> tuple[float, float] | None:
        j, t, l = i - 8, i - 5, i - 3
        if min(j, t, l) < 0 or jaw[j] is None or teeth[t] is None or lips[l] is None:
            return None
        return abs(jaw[j] - teeth[t]), abs(teeth[t] - lips[l])

    k = len(candles) - 1
    now, prev = bars(k), bars(k - 1)
    if now is None or prev is None:
        return None
    return now[0] < prev[0] and now[1] < prev[1]


def macd_turning(candles: Sequence[Candle], direction: Direction) -> bool | None:
    if len(candles) < 40:
        return None
    closes = [c.close for c in candles]
    fast, slow = ema(closes, 12), ema(closes, 26)
    line = [f - s for f, s in zip(fast, slow)]
    signal = ema(line, 9)
    h, hp = line[-1] - signal[-1], line[-2] - signal[-2]
    return (h < 0 and h > hp) if direction is Direction.CALL else (h > 0 and h < hp)


def weis_waves(candles: Sequence[Candle], wave_atr: float = 0.5, atr_n: int = 14) -> tuple[list[list], list | None] | None:
    """(ondas completas [[direção, volume]], onda atual [direção, volume] ou None). None = sem volume."""
    vols = [c.volume or 0.0 for c in candles]
    if not any(vols):
        return None
    closes = [c.close for c in candles]
    waves: list[list] = []
    direction, start, ext = 0, 0, 0
    for i in range(1, len(candles)):
        thr = wave_atr * _atr(candles, i, atr_n)
        if direction == 0:
            if closes[i] - closes[start] >= thr:
                direction, ext = 1, max(range(start, i + 1), key=lambda j: closes[j])
            elif closes[start] - closes[i] >= thr:
                direction, ext = -1, min(range(start, i + 1), key=lambda j: closes[j])
            continue
        if direction == 1:
            if closes[i] >= closes[ext]:
                ext = i
            elif closes[ext] - closes[i] >= thr:
                waves.append([1, sum(vols[start:ext + 1])])
                start, direction, ext = ext + 1, -1, i
        else:
            if closes[i] <= closes[ext]:
                ext = i
            elif closes[i] - closes[ext] >= thr:
                waves.append([-1, sum(vols[start:ext + 1])])
                start, direction, ext = ext + 1, 1, i
    current = [direction, sum(vols[start:])] if direction else None
    return waves, current


def weis_exhausted(candles: Sequence[Candle], direction: Direction, cfg: ConfluenceConfig = ConfluenceConfig()) -> bool | None:
    got = weis_waves(candles, cfg.wave_atr, cfg.atr_period)
    if got is None:
        return None  # sem volume (OTC da IQ)
    waves, current = got
    move = -1 if direction is Direction.CALL else 1  # o movimento que a entrada contraria
    same = [w for w in waves if w[0] == move] + ([current] if current and current[0] == move else [])
    if len(same) < 2:
        return None
    return same[-1][1] < same[-2][1]


def fractal_near(candles: Sequence[Candle], direction: Direction, cfg: ConfluenceConfig = ConfluenceConfig()) -> bool | None:
    k = len(candles) - 1
    if k < 6:
        return None
    tol = cfg.fractal_atr * _atr(candles, k, cfg.atr_period)
    for j in range(k - 2, max(1, k - cfg.fractal_lookback), -1):  # confirmado: duas velas depois dele já fecharam
        around = candles[j - 2:j] + candles[j + 1:j + 3]
        if direction is Direction.CALL and all(candles[j].low < c.low for c in around):
            return abs(candles[k].low - candles[j].low) <= tol
        if direction is Direction.PUT and all(candles[j].high > c.high for c in around):
            return abs(candles[k].high - candles[j].high) <= tol
    return False


def confluences(candles: Sequence[Candle], direction: Direction, cfg: ConfluenceConfig = ConfluenceConfig()) -> dict:
    window = list(candles[-LOOK:])
    return {"gator": gator_sleeping(window), "macd": macd_turning(window, direction),
            "weis": weis_exhausted(window, direction, cfg), "fractal": fractal_near(window, direction, cfg)}


def v2_passes(conf: dict) -> bool:
    """Gator dormindo e MACD virando, obrigatórios; Weis Wave obrigatório só quando há volume. Fractal só anotado."""
    return conf.get("gator") is True and conf.get("macd") is True and conf.get("weis") is not False
