"""Indicadores no mesmo estilo do Quadcode Script (QCS) usado pelos scripts da IQ Option.

Séries são listas alinhadas com as velas; `None` significa "sem valor ainda" (o `na` do QCS).
A inicialização segue a convenção do Pine Script, que o QCS imita:
- `ema` começa no primeiro valor da série;
- `rma` (média de Wilder) começa na média simples dos primeiros `period` valores.
Diferenças de inicialização com a plataforma só afetam as primeiras velas (aquecimento).
"""

from __future__ import annotations

from collections.abc import Sequence

Series = list[float | None]


def change(values: Sequence[float | None]) -> Series:
    out: Series = [None] * len(values)
    for i in range(1, len(values)):
        cur, prev = values[i], values[i - 1]
        out[i] = None if cur is None or prev is None else cur - prev
    return out


def sma(values: Sequence[float | None], period: int) -> Series:
    out: Series = [None] * len(values)
    for i in range(period - 1, len(values)):
        window = values[i - period + 1 : i + 1]
        if all(v is not None for v in window):
            out[i] = sum(window) / period  # type: ignore[arg-type]
    return out


def ema(values: Sequence[float | None], period: int) -> Series:
    alpha = 2.0 / (period + 1)
    out: Series = []
    prev: float | None = None
    for v in values:
        if v is None:
            out.append(None)
            continue
        prev = v if prev is None else alpha * v + (1 - alpha) * prev
        out.append(prev)
    return out


def rma(values: Sequence[float | None], period: int) -> Series:
    alpha = 1.0 / period
    out: Series = []
    prev: float | None = None
    seed: list[float] = []
    for v in values:
        if v is None:
            out.append(None)
            continue
        if prev is None:
            seed.append(v)
            if len(seed) < period:
                out.append(None)
                continue
            prev = sum(seed) / period
        else:
            prev = alpha * v + (1 - alpha) * prev
        out.append(prev)
    return out


def rsi(values: Sequence[float | None], period: int) -> Series:
    ch = change(values)
    up = [None if c is None else max(c, 0.0) for c in ch]
    down = [None if c is None else max(-c, 0.0) for c in ch]
    ru, rd = rma(up, period), rma(down, period)
    out: Series = []
    for u, d in zip(ru, rd):
        if u is None or d is None:
            out.append(None)
        elif d == 0:
            out.append(100.0)
        elif u == 0:
            out.append(0.0)
        else:
            out.append(100.0 - 100.0 / (1.0 + u / d))
    return out


def true_range(high: Sequence[float], low: Sequence[float], close: Sequence[float]) -> Series:
    out: Series = []
    for i in range(len(high)):
        if i == 0:
            out.append(high[i] - low[i])
        else:
            pc = close[i - 1]
            out.append(max(high[i] - low[i], abs(high[i] - pc), abs(low[i] - pc)))
    return out


def highest(values: Sequence[float | None], length: int) -> Series:
    out: Series = [None] * len(values)
    for i in range(length - 1, len(values)):
        window = values[i - length + 1 : i + 1]
        if all(v is not None for v in window):
            out[i] = max(window)  # type: ignore[type-var]
    return out


def lowest(values: Sequence[float | None], length: int) -> Series:
    out: Series = [None] * len(values)
    for i in range(length - 1, len(values)):
        window = values[i - length + 1 : i + 1]
        if all(v is not None for v in window):
            out[i] = min(window)  # type: ignore[type-var]
    return out


def dmi_adx(
    high: Sequence[float], low: Sequence[float], close: Sequence[float], period: int
) -> tuple[Series, Series, Series]:
    """+DI, -DI e ADX com a mesma fórmula manual do script IQ WIKI PRO V2.1.

    Comparações com valor ausente contam como falsas (como no Pine/QCS), então o
    primeiro +DM/-DM vale 0 e não "ausente".
    """
    up_move = change(high)
    down_move = [None if v is None else -v for v in change(low)]
    plus_dm: Series = []
    minus_dm: Series = []
    for up, dn in zip(up_move, down_move):
        ok = up is not None and dn is not None
        plus_dm.append(up if ok and up > dn and up > 0 else 0.0)  # type: ignore[operator]
        minus_dm.append(dn if ok and dn > up and dn > 0 else 0.0)  # type: ignore[operator]

    tr_smooth = rma(true_range(high, low, close), period)
    plus_s, minus_s = rma(plus_dm, period), rma(minus_dm, period)

    plus_di: Series = []
    minus_di: Series = []
    dx: Series = []
    for trs, ps, ms in zip(tr_smooth, plus_s, minus_s):
        if trs is None or ps is None or ms is None:
            plus_di.append(None)
            minus_di.append(None)
            dx.append(None)
            continue
        tr_safe = max(trs, 1e-7)
        pdi, mdi = 100 * ps / tr_safe, 100 * ms / tr_safe
        plus_di.append(pdi)
        minus_di.append(mdi)
        dx.append(100 * abs(pdi - mdi) / max(pdi + mdi, 1e-7))
    return plus_di, minus_di, rma(dx, period)
