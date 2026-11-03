"""Leitura e gravação de velas em CSV (colunas: ts,open,high,low,close,volume)."""

from __future__ import annotations

import csv
from collections.abc import Iterable
from pathlib import Path

from app.market.candle import Candle

FIELDS = ["ts", "open", "high", "low", "close", "volume"]


def write_candles_csv(path: Path, candles: Iterable[Candle]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(FIELDS)
        for c in candles:
            writer.writerow([c.ts, repr(c.open), repr(c.high), repr(c.low), repr(c.close), repr(c.volume)])


def read_candles_csv(path: Path) -> list[Candle]:
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        candles = [
            Candle(
                ts=int(row["ts"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume") or 0.0),
            )
            for row in reader
        ]
    candles.sort(key=lambda c: c.ts)
    return candles
