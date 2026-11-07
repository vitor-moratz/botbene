"""Score LDP v1: em vez de uma estratégia contra a outra, várias juntas decidem a entrada.

Regra CONGELADA em 06/11/2026 (docs/estrategia.md, seção "Score LDP"). Não ajustar números olhando o
resultado: uma versão nova vira outro nome (score_ldp_v2...) e só é medida em dados que ela nunca viu.

A cada vela fechada:
1. As cinco estratégias de dentro da vela (retração no comando, marcações, retração no lote, reversão A e B)
   armam ou não armam. Cada lado (CALL/PUT) ganha pontos: +1 por estratégia armada, +1 por confluência do estudo
   (pág. 26, 41, 102, 110, 162, 177), +1 se a vela não rompeu a máxima/mínima das 10 anteriores, +1 em topos e
   fundos e −1 em consolidação (pág. 223), −1 por estratégia armada do outro lado. Fica o lado com mais pontos;
   empate = pula.
2. A base é a retração no comando (pág. 27, 162): sem ela armada no lado escolhido, não entra.
3. Quatro padrões, 1 ponto cada; entra com pelo menos 3:
   - marcação de comando ou de taxa dividida na marcação (pág. 26, 41);
   - o comando não rompeu a máxima (CALL) / mínima (PUT) das 10 velas anteriores (comando dentro da região);
   - espaço de pelo menos 0,8 ATR até a próxima barreira contrária (pág. 177, 199, 201);
   - recorrência: o combo acertou pelo menos 6 das últimas 10 entradas neste par (desempenho recente, não vem da apostila).
4. Gatilho: o primeiro toque, nos primeiros 15 s da vela seguinte, em qualquer marcação das estratégias do lado
   escolhido (pág. 162). GAP na abertura aborta (pág. 28). Vencimento no fim dessa vela.

A recorrência conta TODAS as entradas do combo no par (o lado escolhido em cada vela, entre ou não), e para isso a
estratégia precisa ver os primeiros 15 s de cada vela: pela pesquisa e na carga do bot, com as velas de 5 s
(`watch_window`); ao vivo, com a vela em formação (`watch_forming`). Sem isso, a recorrência fica ✗.

Medido antes de congelar (ver seção 7 de docs/estrategia.md): 71,1% (128) no período usado para escolher, 62,5% (40)
em 04-06/11 e 63,3% (49) no OTC. A prova vem dos dados a partir de 07/11, com `python -m app.tools.score_check`.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass, field

from app.ldp.engine import EngineStep, LdpEngine
from app.ldp.reading import reading_for
from app.market.candle import Candle
from app.paper import LOSS, WIN, judge
from app.strategies.base import Direction
from app.strategies.ldp_apostila import ArmedSetup, LdpApostila, Plan, gap_ok, touched
from app.strategies.recipes import NAMES as RECIPE_NAMES
from app.strategies.recipes import RecipeConfig, confluences, recipes
from app.strategies.retracao_comando import NAME as RETRACAO
from app.strategies.retracao_comando import RetracaoComando

NAME = "score_ldp"
PATTERNS = ("marcacao", "nao_rompeu", "espaco", "recorrencia")
PATTERN_LABELS = {
    "marcacao": "marcação de comando ou taxa dividida",
    "nao_rompeu": "comando dentro das 10 velas anteriores",
    "espaco": "espaço até a barreira",
    "recorrencia": "recorrência do par",
}
STUDY_CONFS = ("marcacao", "indecisao", "registro", "juntas", "espaco")
PART_LABELS = {RETRACAO: "recuo do comando", "ldp_apostila": "marcação", "retracao_lote": "região do lote",
               "reversao_forca": "defesa da reversão A", "reversao_indecisao": "região da reversão B"}


@dataclass(frozen=True)
class ScoreConfig:
    min_points: int = 3  # dos 4 padrões
    high_low_lookback: int = 10  # o comando não pode ter rompido a máxima/mínima destas velas
    recurrence_size: int = 10  # últimas entradas do combo no par
    recurrence_min: float = 0.6  # acerto mínimo nelas (6 de 10)


@dataclass
class ScoreSetup(ArmedSetup):
    """Um setup com várias marcações: dispara no primeiro toque em qualquer uma delas.

    Cada parte = (marcação, tolerância do toque, recuo a partir da abertura ou None, GAP tolerado). Na abertura
    da vela, as partes que abriram em GAP saem e a marcação do conjunto vira a que o preço encontra primeiro:
    a mais alta no CALL (o preço desce até ela), a mais baixa no PUT.
    """

    parts: list = field(default_factory=list)

    def level_for_open(self, open_price: float) -> float:
        call = self.direction is Direction.CALL
        levels = []
        for level, tol, offset, gap_tol in self.parts:
            if abs(open_price - self.prev_close) > gap_tol:
                continue
            base = level if offset is None else (open_price - offset if call else open_price + offset)
            levels.append(base + tol if call else base - tol)
        if not levels:
            return self.level_price
        return max(levels) if call else min(levels)


def _part(a: ArmedSetup) -> tuple:
    return (a.level_price, a.touch_tol, a.open_offset, max(a.prev_range * a.gap_tol_pct, a.touch_tol, a.gap_floor))


def _side(setups: list[ArmedSetup], opposite: list[ArmedSetup], reading, step: EngineStep, d: int,
          prev: Sequence[Candle], cfg: RecipeConfig) -> tuple[int, set[str], dict[str, bool], bool]:
    names = {s.strategy for s in setups}
    conf = dict.fromkeys(STUDY_CONFS, False)
    for s in setups:
        got = s.confluences if s.strategy in RECIPE_NAMES else confluences(reading, d, s.level_price, [], step.atr, cfg)
        for k in STUDY_CONFS:
            conf[k] = conf[k] or bool(got.get(k))
    c = step.info.candle
    broke = bool(prev) and (c.high > max(x.high for x in prev) if d > 0 else c.low < min(x.low for x in prev))
    scenario = reading.scenarios[-1] if reading.scenarios else None
    points = (len(names) + sum(conf.values()) + (not broke) + (scenario == "topos_fundos")
              - (scenario == "consolidacao") - len({s.strategy for s in opposite}))
    return points, names, conf, not broke


class ScoreLdp:
    name = NAME
    needs_windows = True  # a recorrência precisa ver os primeiros 15 s de cada vela

    def __init__(self, cfg: ScoreConfig | None = None, timeframe: int = 60) -> None:
        self.cfg = cfg or ScoreConfig()
        self.timeframe = timeframe
        self.recipe_cfg = RecipeConfig()
        self.reset()

    def reset(self) -> None:
        tf = self.timeframe
        self.parts = [RetracaoComando(timeframe=tf), LdpApostila(timeframe=tf), *recipes(tf)]
        self.recent: deque[bool] = deque(maxlen=self.cfg.recurrence_size)
        self.watched = False  # alguém já entregou os primeiros segundos de alguma vela
        self._pending: ScoreSetup | None = None  # lado escolhido para a próxima vela (entre ou não), para a recorrência
        self._opened = self._aborted = False
        self._touch: float | None = None

    # ------------------------------------------------------------------ recorrência

    @property
    def recurrence(self) -> tuple[int, int]:
        return sum(self.recent), len(self.recent)

    def _recurrence_ok(self) -> bool:
        wins, n = self.recurrence
        return n == self.cfg.recurrence_size and wins >= self.cfg.recurrence_min * n - 1e-9

    def _see(self, ts: int, open_price: float, low: float, high: float, price: float, in_window: bool) -> None:
        p = self._pending
        if p is None or ts != p.target_ts or self._touch is not None:
            return
        self.watched = True
        if not self._opened:
            self._opened = True
            self._aborted = not gap_ok(p, open_price)
            if not self._aborted:
                p.level_price = p.level_for_open(open_price)
        if not self._aborted and in_window and touched(p, low, high):
            self._touch = price

    def watch_window(self, target_ts: int, subs: Sequence[Candle]) -> None:
        """Velas curtas (5 s) da vela `target_ts`, em ordem: pesquisa e carga do histórico."""
        if not subs:
            return
        for s in subs:
            if s.ts >= target_ts + (self._pending.window_seconds if self._pending else 15):
                break
            self._see(target_ts, subs[0].open, s.low, s.high, s.close, True)

    def watch_forming(self, forming: Candle, now: float) -> None:
        """Ao vivo: a vela em formação, com a máxima e a mínima até agora (o mesmo teste do gatilho do bot)."""
        p = self._pending
        if p is not None:
            self._see(forming.ts, forming.open, forming.low, forming.high, forming.close,
                      now - forming.ts <= p.window_seconds + 1)

    def _settle(self, candle: Candle) -> None:
        p, touch = self._pending, self._touch
        if p is not None and p.target_ts == candle.ts and touch is not None:
            result = judge(p.direction.value, touch, candle.close)
            if result in (WIN, LOSS):
                self.recent.append(result == WIN)
        self._pending, self._touch, self._opened, self._aborted = None, None, False, False

    # ------------------------------------------------------------------ decisão

    def on_step(self, step: EngineStep, engine: LdpEngine) -> Plan:
        self._settle(step.info.candle)
        armed = [a for s in self.parts for a in s.on_step(step, engine).armed]  # todas veem todas as velas
        reading = reading_for(engine, step)
        if not armed or not step.atr or step.atr <= 0:
            return Plan(step.index, [], ["nenhuma estratégia armou nesta vela"])
        calls = [a for a in armed if a.direction is Direction.CALL]
        puts = [a for a in armed if a.direction is Direction.PUT]
        prev = engine.candles[-self.cfg.high_low_lookback - 1:-1]
        sides = []
        for d, mine, other in ((1, calls, puts), (-1, puts, calls)):
            if mine:
                sides.append((d, mine, _side(mine, other, reading, step, d, prev, self.recipe_cfg)))
        sides.sort(key=lambda x: -x[2][0])
        has_rc = [d for d, mine, _ in sides if any(a.strategy == RETRACAO for a in mine)]
        if len(sides) == 2 and sides[0][2][0] == sides[1][2][0]:
            return self._skip(step, has_rc, armed, f"CALL e PUT empataram em {sides[0][2][0]} pontos")
        d, setups, (points, names, conf, inside) = sides[0]
        self._pending = self._composite(step, d, setups, {}, NAME)  # a recorrência acompanha o lado escolhido
        if RETRACAO not in names:
            if has_rc:
                return self._skip(step, has_rc, armed, f"o outro lado teve mais pontos ({points} a {sides[1][2][0]})")
            return Plan(step.index, [], ["sem comando nesta vela (a base do score é a retração no comando)"])
        wins, n = self.recurrence
        marks = {"marcacao": conf["marcacao"], "nao_rompeu": inside, "espaco": conf["espaco"],
                 "recorrencia": self._recurrence_ok()}
        got = sum(marks.values())
        detail = " · ".join(("✓ " if marks[k] else "✗ ") + PATTERN_LABELS[k] for k in PATTERNS)
        rec = f"{wins} de {n}" if n else ("sem histórico ainda" if self.watched else "sem dados dos 15 s")
        side = "CALL" if d > 0 else "PUT"
        if got < self.cfg.min_points:
            text = f"{got} de 4 · {detail} ({rec})"
            return Plan(step.index, [], [f"pulou {side} · {text}"], [self._note(step, d, setups, f"pulou: {text}")])
        setup = self._composite(step, d, setups, marks, NAME, f"{got} de 4 · recorrência {rec}")
        return Plan(step.index, [setup], [])

    def _composite(self, step: EngineStep, d: int, setups: list[ArmedSetup], marks: dict, strategy: str,
                   head: str = "") -> ScoreSetup:
        c = step.info.candle
        rc = next((a for a in setups if a.strategy == RETRACAO), None)
        parts = [_part(a) for a in setups]
        call = d > 0
        guess = [(lv if off is None else (c.close - off if call else c.close + off)) + (tol if call else -tol)
                 for lv, tol, off, _ in parts]
        sources = ([head] if head else []) + sorted({PART_LABELS.get(a.strategy, a.strategy) for a in setups})
        return ScoreSetup(
            direction=Direction.CALL if call else Direction.PUT,
            trigger="score",
            level_price=max(guess) if call else min(guess),
            level_strength=len({a.strategy for a in setups}),
            level_sources=sources,
            decision_index=step.index,
            decision_ts=c.ts,
            target_ts=c.ts + self.timeframe,
            window_seconds=setups[0].window_seconds,
            touch_tol=0.0,
            prev_close=c.close,
            prev_range=c.range,
            gap_tol_pct=0.0,
            confluences=dict(marks),
            strategy=strategy,
            open_offset=rc.open_offset if rc is not None else 0.0,  # sinaliza ao bot que a marcação sai da abertura
            gap_floor=max(p[3] for p in parts),
            parts=parts,
        )

    def _note(self, step: EngineStep, d: int, setups: list[ArmedSetup], outcome: str) -> dict:
        c = step.info.candle
        return {"target_ts": c.ts + self.timeframe, "direction": "call" if d > 0 else "put", "strategy": NAME,
                "setup": "score", "level_price": None, "outcome": outcome}

    def _skip(self, step: EngineStep, has_rc: list[int], armed: list[ArmedSetup], why: str) -> Plan:
        if not has_rc:
            return Plan(step.index, [], [why])
        d = has_rc[0]
        setups = [a for a in armed if (a.direction is Direction.CALL) == (d > 0)]
        side = "CALL" if d > 0 else "PUT"
        return Plan(step.index, [], [f"pulou {side} · {why}"], [self._note(step, d, setups, f"pulou: {why}")])
