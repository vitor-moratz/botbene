from __future__ import annotations

from collections import deque
from collections.abc import Iterable

from app.market.candle import Candle


class CandleStore:
    """Velas fechadas de um ativo/timeframe e a vela em formação.

    O stream da corretora reenvia a vela atual várias vezes por segundo. Quando chega
    uma vela com `ts` maior, a anterior está fechada e é devolvida por `ingest()`.
    As decisões do bot usam só velas fechadas, por isso um sinal já emitido nunca muda.
    """

    def __init__(self, asset: str, timeframe: int, maxlen: int = 2000) -> None:
        self.asset = asset
        self.timeframe = timeframe
        self._closed: deque[Candle] = deque(maxlen=maxlen)
        self._forming: Candle | None = None

    @property
    def closed(self) -> list[Candle]:
        return list(self._closed)

    @property
    def forming(self) -> Candle | None:
        return self._forming

    @property
    def last_closed_ts(self) -> int | None:
        return self._closed[-1].ts if self._closed else None

    def load_history(self, candles: Iterable[Candle]) -> None:
        """Carrega velas já fechadas. Ignora duplicadas e as mais antigas que a última guardada."""
        for candle in sorted(candles, key=lambda c: c.ts):
            last = self.last_closed_ts
            if last is not None and candle.ts <= last:
                continue
            self._closed.append(candle)

    def ingest(self, candle: Candle) -> list[Candle]:
        """Recebe uma atualização do stream e devolve as velas que fecharam com ela."""
        last = self.last_closed_ts
        if last is not None and candle.ts <= last:
            return []  # atualização atrasada de uma vela que já fechou
        if self._forming is None or candle.ts == self._forming.ts:
            self._forming = candle
            return []
        if candle.ts < self._forming.ts:
            return []
        closed = self._forming
        self._closed.append(closed)
        self._forming = candle
        return [closed]

    def close_forming_if_expired(self, now_ts: float) -> list[Candle]:
        """Fecha a vela em formação quando o tempo dela acabou e o stream ainda não mandou a próxima."""
        if self._forming is None or now_ts < self._forming.ts + self.timeframe:
            return []
        closed = self._forming
        self._closed.append(closed)
        self._forming = None
        return [closed]
