"""Bollinger + RCI · fechamento NY: a mesma regra da Bollinger + RCI (bb_rci.py), só com a entrada entre 17:00 e
17:59 de Nova York (hoje 19h de Brasília; de março a novembro, 18h).

Medido em 10–11/11/2026 nos pares -op, entrando na abertura: o dia todo dá 50%; a hora do fechamento de NY deu
53,4% na descoberta e 57,4% na conferência. Com a entrada real do bot, espere uns 3 pontos a menos. OTC: nenhuma
hora se destacou, então ela fica em silêncio no OTC.
"""

from __future__ import annotations

from app.ldp.engine import EngineStep, LdpEngine
from app.market.candle import is_otc
from app.strategies.bb_rci import BollingerRci
from app.strategies.horario_ny import hora_ny
from app.strategies.ldp_apostila import Plan

NAME = "bb_rci_ny"
HORAS_NY = range(17, 18)


class BollingerRciNY(BollingerRci):
    name = NAME

    def __init__(self, cfg=None, timeframe: int = 60) -> None:
        super().__init__(cfg, timeframe)
        self.asset = ""

    def bind_asset(self, asset: str) -> None:
        self.asset = asset

    def on_step(self, step: EngineStep, engine: LdpEngine) -> Plan:
        k = step.info.candle
        if self.asset and is_otc(self.asset):
            return Plan(step.index, [], ["Bollinger NY: só nos pares -op"])
        ny = hora_ny(k.ts + self.timeframe)
        if ny not in HORAS_NY:
            return Plan(step.index, [], [f"Bollinger NY: fora do horário ({ny:02d}h em NY)"])
        return super().on_step(step, engine)
