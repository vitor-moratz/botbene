from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum

from app.market.candle import Candle


class Direction(str, Enum):
    CALL = "call"
    PUT = "put"


@dataclass(frozen=True)
class Signal:
    """Sinal gerado no FECHAMENTO da vela `index`. A entrada acontece na vela seguinte."""

    strategy: str
    index: int
    ts: int
    direction: Direction
    setup: str
    details: dict = field(default_factory=dict, compare=True)


class Strategy(ABC):
    """Uma estratégia olha só velas fechadas e devolve, para cada uma, um sinal ou None."""

    name: str = "base"

    @abstractmethod
    def scan(self, candles: Sequence[Candle]) -> list[Signal | None]:
        """Lista alinhada com `candles`: posição k = sinal no fechamento da vela k."""

    def evaluate_last(self, candles: Sequence[Candle]) -> Signal | None:
        return self.scan(candles)[-1] if candles else None
