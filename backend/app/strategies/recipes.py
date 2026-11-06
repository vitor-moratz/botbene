"""Estratégias da leitura do estudo: Etapa 2 do plano de repaginação.

Regras CONGELADAS em 06/11/2026, antes de medir (docs/estrategia.md, seção 2c). Não ajustar números
olhando o resultado: quem parecer boa vai para a confirmação em dados que nenhuma regra viu.

Todas usam a leitura de app/ldp/reading.py (lotes, regiões, vela de força nas defesas) e armam um setup
para a vela seguinte. A entrada só acontece se o preço tocar a marcação nos primeiros 15 s dela, com
vencimento no fim dessa vela, como as outras estratégias de dentro da vela (pág. 162).

- Retração no lote (pág. 162-172): lote → nova alta/baixa + nova posição → o preço volta à região.
- Reversão A, força trava e reverte (pág. 30, 44, 153, 197, 218): uma vela de força vai até uma defesa
  contrária e fecha nela sem romper; a seguinte entra CONTRA a vela de força.
- Reversão B, força rompe a indecisão (pág. 106-119): dupla/tripla posição, uma vela de força ou um
  comando rompe com o corpo; quando o preço volta à região, entra A FAVOR de quem rompeu.

Confluências (pág. 104, 162, 177, 199, 201): cada uma vale 1 ponto, e as reversões precisam de 2.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.ldp.candles import CandleClass as K
from app.ldp.engine import EngineStep, LdpEngine
from app.ldp.reading import ReadingEngine, Region, reading_for
from app.strategies.base import Direction
from app.strategies.ldp_apostila import ArmedSetup, Plan

RETRACAO_LOTE = "retracao_lote"
REVERSAO_FORCA = "reversao_forca"
REVERSAO_INDECISAO = "reversao_indecisao"
NAMES = (RETRACAO_LOTE, REVERSAO_FORCA, REVERSAO_INDECISAO)

MARCACAO = ("C1", "C2", "TD", "TD1", "TD2", "TD3", "TDI", "TDT", "TDF", "DV")
INDECISAO = ("DP", "TP", "FA", "FB")
REGISTRO = ("NA", "NB")

CONFLUENCE_LABELS = {
    "marcacao": "marcação de comando ou taxa dividida",
    "indecisao": "dupla/tripla posição",
    "registro": "primeiro registro + nova posição",
    "juntas": "duas ou mais marcações juntas",
    "espaco": "espaço até a barreira",
}


@dataclass(frozen=True)
class RecipeConfig:
    window_seconds: int = 15  # gatilho nos primeiros 10-15 s (pág. 27, 162)
    reach_atr: float = 0.6  # região a no máximo isto × ATR do fechamento (o mesmo das marcações)
    level_tol_atr: float = 0.15  # região "na marcação": a até isto × ATR do preço
    touch_tol_atr: float = 0.05
    room_atr: float = 0.8  # espaço mínimo até a próxima barreira contrária
    gap_tol_pct: float = 0.10  # GAP na abertura = abortar (pág. 28)
    min_confluences: int = 2  # reversões
    throwback_candles: int = 5  # reversão B: até quantas velas depois do rompimento a volta ainda vale
    min_candles: int = 30


class _Recipe:
    name = ""
    trigger = "retracao"
    needs_confluences = False

    def __init__(self, cfg: RecipeConfig | None = None, timeframe: int = 60) -> None:
        self.cfg = cfg or RecipeConfig()
        self.timeframe = timeframe

    def reset(self) -> None:  # a leitura fica no motor do par (reading_for)
        pass

    def on_step(self, step: EngineStep, engine: LdpEngine) -> Plan:
        reading = reading_for(engine, step)
        atr = step.atr
        if atr is None or atr <= 0 or len(engine.candles) < self.cfg.min_candles:
            return Plan(step.index, [], ["aquecendo (poucas velas)"])
        candidates, reasons = self.candidates(step, engine, reading, atr)
        armed = []
        for direction, level, regions in candidates:
            conf = confluences(reading, direction, level, regions, atr, self.cfg)
            score = sum(conf.values())
            if self.needs_confluences and score < self.cfg.min_confluences:
                missing = ", ".join(CONFLUENCE_LABELS[k] for k, v in conf.items() if not v)
                reasons.append(f"{'CALL' if direction > 0 else 'PUT'}: {score} de {self.cfg.min_confluences} confluências (faltou: {missing})")
                continue
            armed.append(self._setup(step, direction, level, regions, conf, reading, atr))
        if len({a.direction for a in armed}) > 1:
            return Plan(step.index, [], ["CALL e PUT ao mesmo tempo: leitura contraditória"])
        return Plan(step.index, armed[:1], [] if armed else reasons)

    def candidates(self, step: EngineStep, engine: LdpEngine, reading: ReadingEngine,
                   atr: float) -> tuple[list[tuple[int, float, list[Region]]], list[str]]:
        raise NotImplementedError

    def _setup(self, step: EngineStep, direction: int, level: float, regions: list[Region], conf: dict,
               reading: ReadingEngine, atr: float) -> ArmedSetup:
        c = step.info.candle
        sources = [f"{r.label} (pág. {r.page})" for r in regions]
        scenario = reading.scenarios[-1] if reading.scenarios else None
        if scenario:
            sources.append(f"cenário: {scenario}")
        return ArmedSetup(
            direction=Direction.CALL if direction > 0 else Direction.PUT,
            trigger=self.trigger,
            level_price=level,
            level_strength=len(regions),
            level_sources=sources,
            decision_index=step.index,
            decision_ts=c.ts,
            target_ts=c.ts + self.timeframe,
            window_seconds=self.cfg.window_seconds,
            touch_tol=self.cfg.touch_tol_atr * atr,
            prev_close=c.close,
            prev_range=c.range,
            gap_tol_pct=self.cfg.gap_tol_pct,
            confluences=conf,
            strategy=self.name,
        )


def near_edge(region: Region, direction: int) -> float:
    """A borda da região que o preço encontra ao voltar: o topo de uma região de compra, o fundo de uma de venda."""
    return region.high if direction > 0 else region.low


def at_level(reading: ReadingEngine, level: float, tol: float, direction: int) -> list[Region]:
    """Regiões ativas na marcação, do lado da entrada (ou indecisão ainda sem lado)."""
    return [r for r in reading.active_regions() if r.side in (direction, 0) and r.low - tol <= level <= r.high + tol]


def confluences(reading: ReadingEngine, direction: int, level: float, regions: list[Region], atr: float,
                cfg: RecipeConfig) -> dict[str, bool]:
    near = {r.id: r for r in [*regions, *at_level(reading, level, cfg.level_tol_atr * atr, direction)]}
    codes = {r.code for r in near.values()}
    if direction > 0:  # CALL: a próxima resistência acima
        barriers = [r.low - level for r in reading.active_regions() if r.side < 0 and r.low > level]
    else:
        barriers = [level - r.high for r in reading.active_regions() if r.side > 0 and r.high < level]
    return {
        "marcacao": bool(codes & set(MARCACAO)),
        "indecisao": bool(codes & set(INDECISAO)),
        "registro": bool(codes & set(REGISTRO)),
        "juntas": len(near) >= 2,
        "espaco": not barriers or min(barriers) >= cfg.room_atr * atr,
    }


def _nearest(close: float, regions: list[tuple[float, Region]], direction: int, reach: float) -> tuple[float, Region] | None:
    """A região mais perto do fechamento, do lado certo (abaixo para CALL, acima para PUT) e ao alcance."""
    ok = [(level, r) for level, r in regions
          if (close >= level if direction > 0 else close <= level) and abs(close - level) <= reach]
    return min(ok, key=lambda x: abs(close - x[0]), default=None)


class RetracaoLote(_Recipe):
    """Pág. 162: identifique o lote, marque a nova alta/baixa + nova posição e aguarde o preço buscar a marcação."""

    name = RETRACAO_LOTE
    trigger = "retracao"

    def candidates(self, step, engine, reading, atr):
        close = step.info.candle.close
        out = []
        for direction in (1, -1):
            regions = [(near_edge(r, direction), r) for r in reading.active_regions()
                       if r.code in REGISTRO and r.side == direction and r.label.endswith("nova posição")]
            found = _nearest(close, regions, direction, self.cfg.reach_atr * atr)
            if found:
                out.append((direction, found[0], [found[1]]))
        return out, [] if out else ["nenhuma região de nova alta/baixa + nova posição ao alcance"]


class ReversaoForca(_Recipe):
    """Reversão A: a vela de força travou numa defesa contrária; a seguinte entra contra ela ("travou reverte", pág. 197)."""

    name = REVERSAO_FORCA
    trigger = "reversao"
    needs_confluences = True

    def candidates(self, step, engine, reading, atr):
        hits = reading.defense_hits
        if not hits:
            return [], ["nenhuma vela de força travada numa defesa"]
        direction = -step.info.direction  # as regiões travadas são do lado da entrada
        close = step.info.candle.close
        level = min((near_edge(r, direction) for r in hits), key=lambda p: abs(p - close))
        return [(direction, level, list(hits))], []


class ReversaoIndecisao(_Recipe):
    """Reversão B: indecisão rompida pelo corpo de uma vela de força ou de um comando; entra na volta à região (pág. 106, 119)."""

    name = REVERSAO_INDECISAO
    trigger = "throwback"
    needs_confluences = True

    def candidates(self, step, engine, reading, atr):
        close, i = step.info.candle.close, step.index
        regions = []
        for r in reading.active_regions():
            if r.code not in INDECISAO or r.resolved is None or not 0 <= i - r.resolved <= self.cfg.throwback_candles:
                continue
            breaker = engine.infos[r.resolved]
            strong = reading.impulse(engine, r.resolved) or breaker.cls in (K.C1, K.C2)
            if strong and breaker.direction == r.side:
                regions.append((near_edge(r, r.side), r))
        out = []
        for direction in (1, -1):
            found = _nearest(close, [x for x in regions if x[1].side == direction], direction, self.cfg.reach_atr * atr)
            if found:
                out.append((direction, found[0], [found[1]]))
        return out, [] if out else ["nenhuma indecisão rompida por vela de força ou comando ao alcance"]


def recipes(timeframe: int = 60) -> list:
    return [RetracaoLote(timeframe=timeframe), ReversaoForca(timeframe=timeframe), ReversaoIndecisao(timeframe=timeframe)]
