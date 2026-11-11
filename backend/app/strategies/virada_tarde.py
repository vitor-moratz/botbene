"""Padrão Moratz · Virada da Tarde (regras M-001 e M-002, docs/padrao_moratz/regras/).

Só nos pares -op, com a ENTRADA entre 16:00 e 17:59 de Nova York (o fechamento do dia do forex é às 17h de NY;
hoje, fora do horário de verão americano, isso é 18:00–19:59 de Brasília; de março a novembro, 17:00–18:59):
- vela k fecha colada na máxima (fecho = (fech − mín) ÷ amplitude ≥ 0,83) → PUT na vela k+1;
- vela k fecha colada na mínima (fecho ≤ 0,17) → CALL na vela k+1.
Mesma "vela pronta" do laboratório: as 20 velas anteriores sem buraco e com amplitude mediana > 0.
Entrada no 1º preço da vela seguinte, como a Bollinger + RCI.

Medido em 10/11/2026: 57–58% na descoberta e 55% na conferência entrando na ABERTURA, mas ~52% entrando após a
1ª vela de 5 s, que é o que o bot consegue (empate 54,6%). O efeito vive nos primeiros segundos da vela.
"""

from __future__ import annotations

import statistics

from app.ldp.engine import EngineStep, LdpEngine
from app.market.candle import is_otc
from app.strategies.base import Direction
from app.strategies.horario_ny import hora_ny
from app.strategies.ldp_apostila import ArmedSetup, Plan

NAME = "virada_tarde"
HORAS_NY = range(16, 18)  # hora de Nova York da vela de entrada
TOPO = 0.83
FUNDO = 0.17
JANELA = 20
BRT_OFFSET = -3 * 3600


class ViradaTarde:
    name = NAME

    def __init__(self, cfg=None, timeframe: int = 60, horas_ny: range | None = HORAS_NY) -> None:
        self.timeframe = timeframe
        self.horas_ny = horas_ny  # None = sem filtro de horário (só para comparar com o laboratório)
        self.asset = ""

    def reset(self) -> None:
        pass

    def bind_asset(self, asset: str) -> None:
        self.asset = asset

    def on_step(self, step: EngineStep, engine: LdpEngine) -> Plan:
        k = step.info.candle
        if self.asset and is_otc(self.asset):
            return Plan(step.index, [], ["Virada da Tarde: só nos pares -op"])
        hora = ((k.ts + self.timeframe + BRT_OFFSET) // 3600) % 24
        ny = hora_ny(k.ts + self.timeframe)
        if self.horas_ny is not None and ny not in self.horas_ny:
            return Plan(step.index, [], [f"Virada da Tarde: fora do horário ({ny:02d}h em NY)"])
        velas = engine.candles[-(JANELA + 1):]
        if len(velas) < JANELA + 1 or velas[-1].ts - velas[0].ts != JANELA * self.timeframe:
            return Plan(step.index, [], ["Virada da Tarde: faltam 20 velas seguidas"])
        unidade = statistics.median(v.high - v.low for v in velas[:-1])
        amp = k.high - k.low
        if unidade <= 0 or amp <= 0:
            return Plan(step.index, [], ["Virada da Tarde: mercado parado"])
        fecho = (k.close - k.low) / amp
        if fecho >= TOPO:
            direction, why = Direction.PUT, f"fechou no topo ({fecho:.0%})"
        elif fecho <= FUNDO:
            direction, why = Direction.CALL, f"fechou no fundo ({fecho:.0%})"
        else:
            return Plan(step.index, [], [f"Virada da Tarde: fechou no meio ({fecho:.0%})"])
        setup = ArmedSetup(
            direction=direction,
            trigger=NAME,
            level_price=k.close,
            level_strength=0,
            level_sources=[why],
            decision_index=step.index,
            decision_ts=k.ts,
            target_ts=k.ts + self.timeframe,
            window_seconds=10,
            touch_tol=1e9,  # entra no 1º preço da vela seguinte; GAP não aborta
            prev_close=k.close,
            prev_range=amp,
            gap_tol_pct=0.0,
            confluences={},
            strategy=self.name,
            extra={"fecho": round(fecho, 3), "hora": int(hora), "hora_ny": ny, "tamanho": round(amp / unidade, 2)},
        )
        return Plan(step.index, [setup], [])
