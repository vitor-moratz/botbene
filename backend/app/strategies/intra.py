"""Estratégias que entram DENTRO da vela: no fechamento da vela k armam um setup para a vela k+1,
e a entrada só acontece se o gatilho disparar nos primeiros segundos dela."""

from __future__ import annotations

from collections.abc import Sequence

from app.ldp.engine import EngineStep, LdpEngine
from app.market.candle import Candle
from app.strategies.ldp_apostila import NAME as APOSTILA
from app.strategies.ldp_apostila import LdpApostila, Plan
from app.strategies.recipes import NAMES as RECIPE_NAMES
from app.strategies.recipes import RETRACAO_LOTE, REVERSAO_FORCA, REVERSAO_INDECISAO, recipes
from app.strategies.retracao_comando import NAME as RETRACAO
from app.strategies.retracao_comando import RetracaoComando

INTRA_NAMES = (RETRACAO, APOSTILA, *RECIPE_NAMES)
SHORT_LABELS = {RETRACAO: "Retração no comando", APOSTILA: "Marcações", RETRACAO_LOTE: "Retração no lote",
                REVERSAO_FORCA: "Reversão A", REVERSAO_INDECISAO: "Reversão B"}


def default_intra(timeframe: int = 60) -> list:
    return [RetracaoComando(timeframe=timeframe), LdpApostila(timeframe=timeframe), *recipes(timeframe)]


def plan_all(strategies: Sequence, step: EngineStep, engine: LdpEngine) -> Plan:
    armed, reasons = [], []
    for strat in strategies:
        plan = strat.on_step(step, engine)
        armed += plan.armed
        reasons += [f"{SHORT_LABELS.get(strat.name, strat.name)}: {r}" for r in plan.reasons]
    return Plan(step.index, armed, reasons)


def run_intra(candles: Sequence[Candle], strategies: Sequence | None = None, timeframe: int = 60) -> tuple[LdpEngine, list[Plan]]:
    engine = LdpEngine()
    strategies = strategies if strategies is not None else default_intra(timeframe)
    plans = [plan_all(strategies, engine.process(c), engine) for c in candles]
    return engine, plans
