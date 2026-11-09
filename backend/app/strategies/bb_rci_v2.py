"""Pesquisa · Bollinger + RCI v2: a v1 com confluências (Gator, MACD e Weis Wave), só para observar.

Pedido do usuário em 09/11/2026: medir daqui para frente, no ao vivo, se as confluências deixam a Bollinger mais
assertiva. A regra foi congelada antes de qualquer resultado (mudar = outra versão, com outro nome):
1. Gatilho: o mesmo da v1 (bb_rci.decide): banda de Bollinger 20/2 tocada com o RCI 9 em ±80, entra contra.
2. E as confluências (bb_rci_confluencias.py): Gator dormindo, MACD virando a favor e, onde há volume (pares normais;
   no OTC a IQ manda volume zero), Weis Wave com a onda atual mais fraca que a anterior. O fractal só é anotado.
3. Entrada no início da vela seguinte, vencimento no fim dela (igual à v1).
Só Observar: a configuração recusa Operar. Régua combinada em 09/11: vira Operar se, nos mesmos dias ao vivo, tiver
pelo menos 5 pontos a mais de acerto por entrada que a v1 (150+ entradas da v2), ou menos de 1 ciclo de G2 perdido a
cada 11.
"""

from __future__ import annotations

from app.ldp.engine import EngineStep, LdpEngine
from app.strategies.base import Direction
from app.strategies.bb_rci import BbRciConfig, decide
from app.strategies.bb_rci_confluencias import LOOK, confluences, v2_passes
from app.strategies.ldp_apostila import ArmedSetup, Plan

NAME = "bb_rci_v2"
_LABELS = {"gator": ("Gator dormindo", "Gator acordado"), "macd": ("MACD virando", "MACD sem virar"),
           "weis": ("Weis mais fraca", "Weis mais forte"), "fractal": ("perto do fractal", "longe do fractal")}


def describe(conf: dict) -> str:
    parts = []
    for key in ("gator", "macd", "weis", "fractal"):
        v = conf.get(key)
        if v is None:
            parts.append("Weis sem volume" if key == "weis" else f"{_LABELS[key][0].split()[0]} sem dados")
        else:
            parts.append(_LABELS[key][0 if v else 1])
    return " · ".join(parts)


class BollingerRciV2:
    name = NAME

    def __init__(self, cfg: BbRciConfig | None = None, timeframe: int = 60) -> None:
        self.cfg = cfg or BbRciConfig()
        self.timeframe = timeframe

    def reset(self) -> None:  # sem estado próprio: tudo sai das velas do motor
        pass

    def on_step(self, step: EngineStep, engine: LdpEngine) -> Plan:
        k = step.info.candle
        direction, why, _ = decide(engine.candles[-self.cfg.lookback:], self.cfg, self.timeframe)
        if direction is None:
            return Plan(step.index, [], [why])
        conf = confluences(engine.candles[-LOOK:], direction)
        if not v2_passes(conf):
            return Plan(step.index, [], [f"{why}, mas sem as confluências: {describe(conf)}"])
        setup = ArmedSetup(
            direction=direction,
            trigger="bb_rci_v2",
            level_price=k.close,  # entra logo no início da vela seguinte, no preço do momento
            level_strength=0,
            level_sources=[f"{why} · {describe(conf)}"],
            decision_index=step.index,
            decision_ts=k.ts,
            target_ts=k.ts + self.timeframe,
            window_seconds=10,
            touch_tol=1e9,  # sempre "toca": a entrada é no 1º preço da vela seguinte, e GAP não aborta
            prev_close=k.close,
            prev_range=k.high - k.low,
            gap_tol_pct=0.0,
            confluences={},
            strategy=self.name,
            extra={"confluencias": conf},
        )
        return Plan(step.index, [setup], [])
