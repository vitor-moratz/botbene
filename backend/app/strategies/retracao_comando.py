"""Retração no comando: a estratégia que passou na conferência da pesquisa (docs/estrategia.md, seção 7).

Regra (apostila, pág. 27-29: "caso o candle atual entre na região do comando ele será repelido"):
1. A vela k fecha FORTE numa direção: corpo >= 60% da amplitude e amplitude >= 1,5 × ATR, onde ATR é
   a média das amplitudes das 14 velas ANTERIORES a ela.
2. Arma para a vela k+1, a favor da vela k. Vela k+1 aberta em GAP = abortar (pág. 28).
3. Gatilho: nos primeiros 15 s da vela k+1 o preço recua pelo menos 0,8 × ATR a partir da abertura
   dela. Entra nesse momento, a favor da vela k; vencimento no fim da vela k+1.

Medida na base de pesquisa (velas de 5 s para ver dentro do minuto): ajuste 62,0% em 192 entradas;
conferência (período que nenhum ajuste viu) 56,4% em 140; em 6 pares novos, sem ajuste, 53,8% em 303.
Fora da amostra, ~54% — o mesmo que o empate com payout de 84% (54,3%). Melhor estratégia encontrada,
mas sem vantagem comprovada: precisa de confirmação ao vivo.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.ldp.engine import EngineStep, LdpEngine
from app.strategies.base import Direction
from app.strategies.ldp_apostila import ArmedSetup, Plan

NAME = "retracao_comando"


@dataclass(frozen=True)
class RetracaoConfig:
    min_body_ratio: float = 0.6  # corpo / amplitude da vela k
    min_range_atr: float = 1.5  # amplitude da vela k em ATR
    depth_atr: float = 0.8  # recuo mínimo na vela k+1, a partir da abertura
    window_seconds: int = 15
    gap_tol_pct: float = 0.10
    gap_floor_atr: float = 0.05
    atr_period: int = 14


class RetracaoComando:
    name = NAME

    def __init__(self, cfg: RetracaoConfig | None = None, timeframe: int = 60) -> None:
        self.cfg = cfg or RetracaoConfig()
        self.timeframe = timeframe

    def reset(self) -> None:  # sem estado próprio: tudo sai das velas do motor
        pass

    def on_step(self, step: EngineStep, engine: LdpEngine) -> Plan:
        cfg = self.cfg
        candles = engine.candles
        if len(candles) < cfg.atr_period + 1:
            return Plan(step.index, [], ["aquecendo (poucas velas)"])
        k = step.info.candle
        before = candles[-cfg.atr_period - 1:-1]
        atr = sum(c.high - c.low for c in before) / cfg.atr_period
        rng, body = k.high - k.low, k.close - k.open
        if atr <= 0 or rng <= 0 or body == 0:
            return Plan(step.index, [], ["vela sem corpo"])
        if abs(body) < cfg.min_body_ratio * rng:
            return Plan(step.index, [], [f"vela sem força: corpo {abs(body) / rng:.0%} da amplitude (mínimo {cfg.min_body_ratio:.0%})"])
        if rng < cfg.min_range_atr * atr:
            return Plan(step.index, [], [f"vela pequena: {rng / atr:.1f} ATR (mínimo {cfg.min_range_atr:.1f})"])
        direction = Direction.CALL if body > 0 else Direction.PUT
        depth = cfg.depth_atr * atr
        setup = ArmedSetup(
            direction=direction,
            trigger="comando",
            level_price=k.close - depth if direction is Direction.CALL else k.close + depth,
            level_strength=0,
            level_sources=[f"recuo de {cfg.depth_atr:.1f} ATR"],
            decision_index=step.index,
            decision_ts=k.ts,
            target_ts=k.ts + self.timeframe,
            window_seconds=cfg.window_seconds,
            touch_tol=0.0,
            prev_close=k.close,
            prev_range=rng,
            gap_tol_pct=cfg.gap_tol_pct,
            confluences={},
            strategy=NAME,
            open_offset=depth,
            gap_floor=cfg.gap_floor_atr * atr,
        )
        return Plan(step.index, [setup], [])
