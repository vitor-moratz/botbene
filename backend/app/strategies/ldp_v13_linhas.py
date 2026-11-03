"""LDP v1.3 + a regra das linhas proposta pelo usuário (conferida com a apostila em docs/estrategia.md).

Mantém só os sinais do v1.3 que estão do lado certo das DUAS linhas, no fechamento da vela:
- CALL só se o fechamento ficou ACIMA da linha verde e da linha vermelha;
- PUT só se o fechamento ficou ABAIXO das duas;
- no meio das linhas (zona de conflito): descarta.

Isso já cobre a inversão de papel: depois que o corpo rompe a linha verde para baixo,
o preço fica abaixo dela e um PUT ali passa a valer (pág. 95).
"""

from __future__ import annotations

from collections.abc import Sequence

from app.market.candle import Candle
from app.strategies.base import Direction, Signal, Strategy
from app.strategies.ldp_v13 import LdpV13


class LdpV13Linhas(Strategy):
    name = "ldp_v13_linhas"

    def __init__(self, base: LdpV13 | None = None) -> None:
        self.base = base or LdpV13()

    def scan(self, candles: Sequence[Candle]) -> list[Signal | None]:
        res = self.base.analyze(candles)
        out: list[Signal | None] = [None] * len(candles)
        for k, sig in enumerate(res.signals):
            if sig is None:
                continue
            close = candles[k].close
            lines = [v for v in res.lines_after_close(k, candles) if v is not None]
            if sig.direction is Direction.CALL:
                ok = all(close > v for v in lines)
                side = "acima das linhas"
            else:
                ok = all(close < v for v in lines)
                side = "abaixo das linhas"
            if ok:
                details = {**sig.details, "filtro": side}
                out[k] = Signal(self.name, k, sig.ts, sig.direction, sig.setup, details)
        return out
