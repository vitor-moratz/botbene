from __future__ import annotations

from dataclasses import dataclass


def normalize_asset(name: str) -> str:
    """Nome de ativo como a IQ usa: base em maiúsculas; sufixo "-op" (binária de par normal) em
    minúsculas e "-OTC" em maiúsculas. Ex.: "eurusd-OP" -> "EURUSD-op"."""
    base, sep, suffix = name.strip().partition("-")
    if not sep:
        return base.upper()
    return f"{base.upper()}-{'op' if suffix.lower() == 'op' else suffix.upper()}"


def valid_asset(name: str) -> bool:
    return 3 <= len(name) <= 20 and all(ch.isalnum() or ch == "-" for ch in name)


def is_otc(asset: str) -> bool:
    return asset.upper().endswith("-OTC")


@dataclass(frozen=True, slots=True)
class Candle:
    """Uma vela OHLC. `ts` é o início da vela em segundos (epoch UTC)."""

    ts: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    @property
    def is_bull(self) -> bool:
        return self.close > self.open

    @property
    def is_bear(self) -> bool:
        return self.close < self.open

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def range(self) -> float:
        return self.high - self.low

    @property
    def body_top(self) -> float:
        return max(self.open, self.close)

    @property
    def body_bottom(self) -> float:
        return min(self.open, self.close)

    @property
    def upper_wick(self) -> float:
        return self.high - self.body_top

    @property
    def lower_wick(self) -> float:
        return self.body_bottom - self.low

    @property
    def mid(self) -> float:
        """50% do corpo: a marcação de 50% da apostila."""
        return (self.open + self.close) / 2
