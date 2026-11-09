"""Estratégias que entram DENTRO da vela: no fechamento da vela k armam um setup para a vela k+1,
e a entrada só acontece se o gatilho disparar nos primeiros segundos dela."""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Iterable, Sequence

from app.ldp.engine import EngineStep, LdpEngine
from app.market.candle import Candle
from app.strategies.bb_rci import NAME as BB_RCI
from app.strategies.bb_rci import BollingerRci
from app.strategies.bb_rci_v2 import NAME as BB_RCI_V2
from app.strategies.bb_rci_v2 import BollingerRciV2
from app.strategies.deeplob import NAME as DEEPLOB
from app.strategies.deeplob import DeepLobIQ
from app.strategies.esticao import NAME as ESTICAO
from app.strategies.esticao import Esticao
from app.strategies.ldp_apostila import NAME as APOSTILA
from app.strategies.ldp_apostila import LdpApostila, Plan
from app.strategies.recipes import NAMES as RECIPE_NAMES
from app.strategies.recipes import RETRACAO_LOTE, REVERSAO_FORCA, REVERSAO_INDECISAO, recipes
from app.strategies.retracao_comando import NAME as RETRACAO
from app.strategies.retracao_comando import NAME_V2 as RETRACAO_V2
from app.strategies.retracao_comando import RetracaoComando, RetracaoComandoV2
from app.strategies.score import NAME as SCORE
from app.strategies.score import ScoreLdp

INTRA_NAMES = (SCORE, RETRACAO_V2, RETRACAO, APOSTILA, *RECIPE_NAMES, ESTICAO, DEEPLOB, BB_RCI, BB_RCI_V2)
SHORT_LABELS = {SCORE: "Score", RETRACAO_V2: "Retração no comando v2", RETRACAO: "Retração no comando", APOSTILA: "Marcações", RETRACAO_LOTE: "Retração no lote",
                REVERSAO_FORCA: "Reversão A", REVERSAO_INDECISAO: "Reversão B", ESTICAO: "Esticão rápido", DEEPLOB: "DeepLOB",
                BB_RCI: "Bollinger + RCI", BB_RCI_V2: "Bollinger + RCI v2"}
# Estratégias que ainda não podem mandar ordem: só Desligada ou Observar.
OBSERVE_ONLY = (ESTICAO, DEEPLOB, BB_RCI_V2)


def default_intra(timeframe: int = 60) -> list:
    return [ScoreLdp(timeframe=timeframe), RetracaoComandoV2(timeframe=timeframe), RetracaoComando(timeframe=timeframe),
            LdpApostila(timeframe=timeframe),
            *recipes(timeframe), Esticao(timeframe=timeframe), DeepLobIQ(timeframe=timeframe), BollingerRci(timeframe=timeframe),
            BollingerRciV2(timeframe=timeframe)]


def bind_asset(strategies: Sequence, asset: str) -> None:
    """Estratégias que dependem do par (o DeepLOB fica em silêncio nos OTC) recebem o nome dele."""
    for s in strategies:
        if hasattr(s, "bind_asset"):
            s.bind_asset(asset)


def plan_all(strategies: Sequence, step: EngineStep, engine: LdpEngine) -> Plan:
    armed, reasons, skipped = [], [], []
    for strat in strategies:
        plan = strat.on_step(step, engine)
        armed += plan.armed
        reasons += [f"{SHORT_LABELS.get(strat.name, strat.name)}: {r}" for r in plan.reasons]
        skipped += plan.skipped
    return Plan(step.index, armed, reasons, skipped)


def wants_windows(strategies: Sequence) -> bool:
    """Alguma estratégia precisa ver os primeiros segundos de cada vela (o score, para a recorrência)?"""
    return any(getattr(s, "needs_windows", False) for s in strategies)


def watch_forming(strategies: Sequence, forming: Candle, now: float) -> None:
    for s in strategies:
        if getattr(s, "needs_windows", False):
            s.watch_forming(forming, now)


def replay(strategies: Sequence, engine: LdpEngine, candles: Sequence[Candle], subs: Iterable[Candle] | None = None,
           timeframe: int = 60) -> tuple[list[Plan], EngineStep | None]:
    """Passa as velas fechadas pelas estratégias, em ordem. Com as velas de 5 s, quem precisa vê os
    primeiros segundos de cada vela antes do fechamento dela (como ao vivo)."""
    windowed = [s for s in strategies if getattr(s, "needs_windows", False)] if subs is not None else []
    sub_list = sorted(subs, key=lambda s: s.ts) if windowed else []
    keys = [s.ts for s in sub_list]
    plans, step = [], None
    for c in candles:
        if windowed:
            inside = sub_list[bisect_left(keys, c.ts):bisect_left(keys, c.ts + timeframe)]
            for s in windowed:
                s.watch_window(c.ts, inside)
        step = engine.process(c)
        plans.append(plan_all(strategies, step, engine))
    return plans, step


def run_intra(candles: Sequence[Candle], strategies: Sequence | None = None, timeframe: int = 60,
              subs: Iterable[Candle] | None = None) -> tuple[LdpEngine, list[Plan]]:
    engine = LdpEngine()
    strategies = strategies if strategies is not None else default_intra(timeframe)
    plans, _ = replay(strategies, engine, candles, subs, timeframe)
    return engine, plans
