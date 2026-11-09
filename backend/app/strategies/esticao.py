"""Esticão rápido: estratégia própria, tirada dos dados (estudo de 08/11/2026, docs/estrategia.md seção A3).

Ideia: quando o preço dispara muito logo nos primeiros segundos do minuto, depois de uma vela grande, o
disparo costuma ser exagero e volta um pouco até o fim da vela. Entra CONTRA o disparo.

Regra (congelada em 08/11/2026; uma mudança vira outra versão, com outro nome):
1. ATR = média das amplitudes das 14 últimas velas fechadas, contando a vela k que acabou de fechar.
2. A vela k é grande: amplitude >= 1,5 ATR (qualquer cor).
3. Arma os dois lados para a vela k+1, com o nível medido a partir da abertura dela:
   PUT em abertura + 1,5 ATR e CALL em abertura - 1,5 ATR. Vale o lado que tocar primeiro.
4. Vela k+1 aberta com GAP maior que 0,1 ATR: aborta.
5. Gatilho só nos 10 s iniciais. Vencimento no fim da vela k+1.

Números do estudo (pares -op, velas de 5 s): 73% em 82 entradas no período de escolha (02 a 04/11);
na conferência (05 e 06/11), 44% entrando no exato toque e 61% no fechamento da vela de 5 s do toque,
com só 18 entradas. Nos OTC não funcionou (~45-50%). Por isso fica só em Observar: Operar é recusado
na configuração até ela provar acerto ao vivo.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.ldp.engine import EngineStep, LdpEngine
from app.strategies.base import Direction
from app.strategies.ldp_apostila import ArmedSetup, Plan

NAME = "esticao"


@dataclass(frozen=True)
class EsticaoConfig:
    min_prev_range_atr: float = 1.5  # amplitude da vela k em ATR
    stretch_atr: float = 1.5  # distância da abertura da vela k+1 até o gatilho
    window_seconds: int = 10
    gap_max_atr: float = 0.1
    atr_period: int = 14


class Esticao:
    name = NAME

    def __init__(self, cfg: EsticaoConfig | None = None, timeframe: int = 60) -> None:
        self.cfg = cfg or EsticaoConfig()
        self.timeframe = timeframe

    def reset(self) -> None:  # sem estado próprio: tudo sai das velas do motor
        pass

    def on_step(self, step: EngineStep, engine: LdpEngine) -> Plan:
        cfg = self.cfg
        candles = engine.candles
        if len(candles) < cfg.atr_period:
            return Plan(step.index, [], ["aquecendo (poucas velas)"])
        k = step.info.candle
        atr = sum(c.high - c.low for c in candles[-cfg.atr_period:]) / cfg.atr_period
        rng = k.high - k.low
        if atr <= 0:
            return Plan(step.index, [], ["sem amplitude"])
        if rng < cfg.min_prev_range_atr * atr:
            return Plan(step.index, [], [f"vela pequena: {rng / atr:.1f} ATR (mínimo {cfg.min_prev_range_atr:.1f})"])
        offset = cfg.stretch_atr * atr
        armed = [self._setup(step, k, Direction.PUT, offset, atr, rng),
                 self._setup(step, k, Direction.CALL, offset, atr, rng)]
        return Plan(step.index, armed, [])

    def _setup(self, step: EngineStep, k, direction: Direction, offset: float, atr: float, rng: float) -> ArmedSetup:
        cfg = self.cfg
        side = "para cima" if direction is Direction.PUT else "para baixo"
        return ArmedSetup(
            direction=direction,
            trigger="esticao",
            # Estimativa até a vela abrir; na abertura, o bot recalcula a partir dela (open_offset).
            level_price=k.close + offset if direction is Direction.PUT else k.close - offset,
            level_strength=0,
            level_sources=[f"disparo de {cfg.stretch_atr:.1f} ATR {side}"],
            decision_index=step.index,
            decision_ts=k.ts,
            target_ts=k.ts + self.timeframe,
            window_seconds=cfg.window_seconds,
            touch_tol=0.0,
            prev_close=k.close,
            prev_range=rng,
            gap_tol_pct=0.0,
            confluences={},
            strategy=self.name,
            open_offset=offset,
            gap_floor=cfg.gap_max_atr * atr,
        )
