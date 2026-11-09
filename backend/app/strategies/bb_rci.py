"""Pesquisa · Bollinger + RCI: reversão quando o preço estica até a banda e o RCI está no extremo.

Regra (pedido do usuário em 09/11/2026; a versão "padrão" foi fixada antes de olhar qualquer número):
1. Bandas de Bollinger: média simples de 20 fechamentos, ± 2 desvios-padrão (populacional, como na IQ).
2. RCI (Rank Correlation Index) de 9 fechamentos: compara a ordem no tempo com a ordem no preço.
   +100 = os 9 subiram em fila; -100 = caíram em fila. Empates de preço recebem a posição média.
3. PUT: a vela k chegou na banda de cima (máxima >= banda) e o RCI está em +80 ou mais.
   CALL: a vela k chegou na banda de baixo (mínima <= banda) e o RCI está em -80 ou menos.
4. Entrada logo no início da vela k+1; vencimento no fim dela (1 min).
5. Precisa das últimas velas seguidas, sem buraco; se faltar vela, não decide.

Variações (só para o estudo): banda de 2,5 ou 3 desvios, "fechou fora" em vez de "tocou",
RCI de 14, nível 90 e "RCI virando" (para PUT, o RCI caiu em relação à vela anterior).

Estudo de 09/11/2026 (docs/estrategia.md, seção A5; velas M1 de 09/09 a 08/11): cara ou coroa.
Padrão: 50,0% (33.841) nos -op e 50,1% (33.388) nos OTC no período de conferência. A melhor das 96
variações não passou de 53% na escolha e não se repetiu na conferência. Martingale (G1/G2, imediato ou
"com análise") não virou nenhuma para o lucro.

No bot desde 09/11/2026, a pedido do usuário, apesar do estudo: começa Desligada e pode Observar ou Operar.
Anota ~1 entrada a cada 8 min por par (dispara bem mais que as outras).
"""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence
from dataclasses import dataclass

from app.ldp.engine import EngineStep, LdpEngine
from app.market.candle import Candle
from app.strategies.base import Direction
from app.strategies.ldp_apostila import ArmedSetup, Plan

log = logging.getLogger(__name__)

NAME = "bb_rci"


@dataclass(frozen=True)
class BbRciConfig:
    bb_period: int = 20
    bb_std: float = 2.0
    rci_period: int = 9
    rci_level: float = 80.0
    contact: str = "toque"  # "toque": máxima/mínima chegou na banda; "fechou": fechamento fora da banda
    rci_turn: bool = False  # exige o RCI virando a favor da entrada

    @property
    def lookback(self) -> int:
        """Quantas velas seguidas (terminando na vela k) a decisão precisa."""
        return max(self.bb_period, self.rci_period + (1 if self.rci_turn else 0))


def rci(closes: Sequence[float]) -> float:
    """RCI dos fechamentos dados (o último é o mais novo), de -100 a +100."""
    n = len(closes)
    if n < 2:
        return 0.0
    total = 0.0
    for j, x in enumerate(closes):
        time_rank = n - j  # mais novo = 1
        above = sum(1 for y in closes if y > x)
        ties = sum(1 for y in closes if y == x)
        price_rank = 1 + above + (ties - 1) / 2  # maior preço = 1
        total += (time_rank - price_rank) ** 2
    return (1 - 6 * total / (n * (n * n - 1))) * 100


def bollinger(closes: Sequence[float], std_mult: float) -> tuple[float, float, float]:
    """(média, banda de cima, banda de baixo) dos fechamentos dados."""
    n = len(closes)
    mid = sum(closes) / n
    sd = math.sqrt(sum((c - mid) ** 2 for c in closes) / n)
    return mid, mid + std_mult * sd, mid - std_mult * sd


def contiguous(candles: Sequence[Candle], n: int, timeframe: int = 60) -> bool:
    """As últimas `n` velas são seguidas (sem buraco)?"""
    return len(candles) >= n and candles[-1].ts - candles[-n].ts == (n - 1) * timeframe


def decide(candles: Sequence[Candle], cfg: BbRciConfig, timeframe: int = 60) -> tuple[Direction | None, str, dict]:
    """Decisão no fechamento da última vela de `candles`. Devolve (direção ou None, motivo, números)."""
    if not contiguous(candles, cfg.lookback, timeframe):
        return None, "aquecendo (faltam velas seguidas)", {}
    k = candles[-1]
    closes = [c.close for c in candles[-cfg.lookback:]]
    mid, up, lo = bollinger(closes[-cfg.bb_period:], cfg.bb_std)
    r = rci(closes[-cfg.rci_period:])
    nums = {"rci": round(r, 1), "upper": up, "lower": lo, "mid": mid}
    if cfg.contact == "fechou":
        hit_up, hit_lo = k.close > up, k.close < lo
    else:
        hit_up, hit_lo = k.high >= up, k.low <= lo
    if hit_up and r >= cfg.rci_level:
        direction = Direction.PUT
    elif hit_lo and r <= -cfg.rci_level:
        direction = Direction.CALL
    else:
        where = "na banda de cima" if hit_up else "na banda de baixo" if hit_lo else "dentro das bandas"
        return None, f"preço {where}, RCI {r:+.0f}: sem entrada", nums
    if cfg.rci_turn:
        prev = rci(closes[-cfg.rci_period - 1:-1])
        nums["rci_prev"] = round(prev, 1)
        turned = r < prev if direction is Direction.PUT else r > prev
        if not turned:
            return None, f"RCI {r:+.0f} ainda não virou (antes {prev:+.0f})", nums
    side = "de cima" if direction is Direction.PUT else "de baixo"
    return direction, f"banda {side} + RCI {r:+.0f}", nums


class BollingerRci:
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
        extra = {}
        try:  # só anota as confluências da v2 (não decide nada); um erro aqui nunca impede a entrada
            from app.strategies.bb_rci_confluencias import LOOK, confluences
            extra = {"confluencias": confluences(engine.candles[-LOOK:], direction)}
        except Exception:  # noqa: BLE001
            log.exception("Bollinger + RCI: confluências")
        setup = ArmedSetup(
            direction=direction,
            trigger="bb_rci",
            level_price=k.close,  # entra logo no início da vela seguinte, no preço do momento
            level_strength=0,
            level_sources=[why],
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
            extra=extra,
        )
        return Plan(step.index, [setup], [])
