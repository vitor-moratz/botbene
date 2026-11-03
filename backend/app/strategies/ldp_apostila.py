"""Estratégia da apostila: entradas DENTRO da vela, nas marcações.

Como funciona (detalhes em docs/estrategia.md):
1. No fechamento da vela k, olha o mapa de marcações do motor e ARMA no máximo um setup por
   direção para a vela k+1: a marcação mais próxima do lado certo (suporte para CALL, resistência
   para PUT), forte o bastante e ao alcance de uma retração. "Caso o candle atual entre na região
   do comando ele será repelido" (pág. 27).
2. Tipo do setup:
   - retração: pullback para a mesma vela (pág. 28-29);
   - reversão: a vela k, contra o movimento, fechou travando o corpo na marcação (pág. 30, 44);
   - throwback: a vela k rompeu a marcação com o corpo e ela trocou de papel (pág. 31, 45).
3. Gatilho: só entra se o preço TOCAR a marcação nos primeiros `window_seconds` (15 s) da vela
   k+1; vencimento no fim dessa vela. "Passado esse tempo sem ter ido buscar a marcação, não faça
   nada" (pág. 162). GAP na abertura = abortar (pág. 28).
4. Confluências independentes, 1 ponto cada, mínimo 3 (pág. 162 + resumo V2): gatilho, força da
   marcação, contexto (nova alta/baixa + nova posição), espaço até a barreira, tendência (EMA 9/21).
5. Vetos: regra das linhas do usuário (CALL só acima das duas, PUT só abaixo), suporte/resistência
   espremidos (pág. 106, 223), indecisão/dupla/tripla (pág. 106-111), consolidação (pág. 223),
   pernada íngreme para retração (pág. 131), CALL e PUT ao mesmo tempo.
"""

from __future__ import annotations

from bisect import bisect_left
from collections import deque
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field, replace

from app.ldp.engine import EngineStep, LdpEngine
from app.ldp.levels import Level, Role
from app.market.candle import Candle
from app.paper import judge
from app.strategies.base import Direction

NAME = "ldp_apostila"
_INDECISION = {"dupla_posicao": "dupla posição", "tripla_posicao": "tripla posição",
               "futuro_alta": "futuro de alta", "futuro_baixa": "futuro de baixa"}
_CLOSE_KINDS = {"fechamento", "defesa_fechamento"}
CONFLUENCE_LABELS = {
    "gatilho": "gatilho da apostila",
    "forca": "marcação forte",
    "contexto": "nova alta/baixa + nova posição",
    "espaco": "espaço até a barreira",
    "tendencia": "tendência (EMA 9/21)",
}


@dataclass(frozen=True)
class ApostilaConfig:
    window_seconds: int = 15  # gatilho de retração: primeiros 10-15 s da vela (pág. 27)
    reach_atr: float = 0.6  # marcação a no máximo isto × ATR do fechamento
    min_distance_atr: float = 0.05  # mais perto que isso é a própria abertura (só vale na reversão)
    touch_tol_atr: float = 0.05  # tolerância para considerar que tocou
    trava_tol_atr: float = 0.15  # reversão: fechamento travado a até isto × ATR da marcação
    min_strength: int = 2
    min_confluences: int = 3
    conflict_atr: float = 0.5  # suporte e resistência mais próximos que isso = preço espremido
    room_atr: float = 0.8  # espaço mínimo até a próxima barreira contrária
    consolidation_window: int = 10
    consolidation_range_atr: float = 2.5  # amplitude das últimas N velas < isso × ATR = consolidado
    steep_ratio: float = 1.2  # pernada "de 60°": deslocamento por vela > isso × ATR
    context_lookback: int = 20
    gap_tol_pct: float = 0.10
    use_lines_rule: bool = True
    ema_fast: int = 9
    ema_slow: int = 21
    min_candles: int = 20


@dataclass
class ArmedSetup:
    direction: Direction
    trigger: str  # "retracao" | "reversao" | "throwback"
    level_price: float
    level_strength: int
    level_sources: list[str]
    decision_index: int
    decision_ts: int
    target_ts: int  # vela de entrada
    window_seconds: int
    touch_tol: float
    prev_close: float
    prev_range: float
    gap_tol_pct: float
    confluences: dict[str, bool] = field(default_factory=dict)
    strategy: str = "ldp_apostila"
    # Marcação relativa à ABERTURA da vela de entrada (recuo de X a partir dela). Enquanto a vela não
    # abre, level_price é uma estimativa a partir do fechamento anterior; na abertura é recalculado.
    open_offset: float | None = None
    gap_floor: float = 0.0  # GAP tolerado no mínimo (em preço), além do % da amplitude

    @property
    def score(self) -> int:
        return sum(self.confluences.values())

    @property
    def setup_label(self) -> str:
        trig = {"retracao": "retração", "reversao": "reversão", "throwback": "throwback",
                "comando": "retração no comando"}[self.trigger]
        return f"{trig} · {self.level_sources[0]}" if self.level_sources else trig

    def level_for_open(self, open_price: float) -> float:
        if self.open_offset is None:
            return self.level_price
        return open_price - self.open_offset if self.direction is Direction.CALL else open_price + self.open_offset

    @property
    def key(self) -> tuple:
        return (self.target_ts, self.direction.value, self.strategy)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["direction"] = self.direction.value
        d["score"] = self.score
        d["setup"] = self.setup_label
        d["window_end"] = self.target_ts + self.window_seconds
        return d


@dataclass
class Plan:
    index: int
    armed: list[ArmedSetup]
    reasons: list[str]


# ---------------------------------------------------------------------- gatilho (vela de entrada)


def gap_ok(setup: ArmedSetup, open_price: float) -> bool:
    gap = abs(open_price - setup.prev_close)
    return gap <= max(setup.prev_range * setup.gap_tol_pct, setup.touch_tol, setup.gap_floor)


def touched(setup: ArmedSetup, low: float, high: float) -> bool:
    if setup.direction is Direction.CALL:
        return low <= setup.level_price + setup.touch_tol
    return high >= setup.level_price - setup.touch_tol


def simulate_entry(setup: ArmedSetup, subcandles: Iterable[Candle]) -> tuple[float | None, str]:
    """Backtest do gatilho com velas curtas (5 s) da vela de entrada. Entrada = fechamento da
    vela curta em que o toque aconteceu (o preço do momento, não o preço ideal da marcação)."""
    end = setup.target_ts + setup.window_seconds
    subs = sorted((s for s in subcandles if setup.target_ts <= s.ts < end), key=lambda s: s.ts)
    if not subs:
        return None, "sem dados intravela"
    if not gap_ok(setup, subs[0].open):
        return None, "GAP na abertura"
    if setup.open_offset is not None:
        setup = replace(setup, level_price=setup.level_for_open(subs[0].open))
    for s in subs:
        if touched(setup, s.low, s.high):
            return s.close, "tocou"
    return None, "não buscou a marcação"


# ---------------------------------------------------------------------- estratégia


class LdpApostila:
    """Estratégia com estado: precisa receber TODAS as velas fechadas em ordem (via on_step)."""

    name = NAME

    def __init__(self, cfg: ApostilaConfig | None = None, timeframe: int = 60) -> None:
        self.cfg = cfg or ApostilaConfig()
        self.timeframe = timeframe
        self.reset()

    def reset(self) -> None:
        self._recent: deque[EngineStep] = deque(maxlen=self.cfg.context_lookback)
        self._ema_f: float | None = None
        self._ema_s: float | None = None
        self._ema_s_prev: float | None = None
        self._green_line: float | None = None  # 50% do último comando de alta (linha verde)
        self._red_line: float | None = None

    # ------------------------------------------------------------------ estado incremental

    def _update(self, step: EngineStep) -> None:
        close = step.info.candle.close
        af, as_ = 2 / (self.cfg.ema_fast + 1), 2 / (self.cfg.ema_slow + 1)
        self._ema_s_prev = self._ema_s
        self._ema_f = close if self._ema_f is None else af * close + (1 - af) * self._ema_f
        self._ema_s = close if self._ema_s is None else as_ * close + (1 - as_) * self._ema_s
        self._recent.append(step)
        for s in step.structures:
            if s.name in ("comando_n1", "comando_unico") and s.detail in ("reversao", "rompimento"):
                if s.direction > 0:
                    self._green_line = step.info.candle.mid
                else:
                    self._red_line = step.info.candle.mid

    def on_step(self, step: EngineStep, engine: LdpEngine) -> Plan:
        self._update(step)
        cfg = self.cfg
        reasons: list[str] = []
        atr = step.atr
        if atr is None or atr <= 0 or len(engine.candles) < cfg.min_candles:
            return Plan(step.index, [], ["aquecendo (poucas velas)"])
        c = step.info.candle

        for s in step.structures:
            if s.name in _INDECISION:
                return Plan(step.index, [], [f"indecisão ({_INDECISION[s.name]}): aguardar vela de força romper"])
        window = engine.candles[-cfg.consolidation_window:]
        if len(window) == cfg.consolidation_window:
            amp = max(x.high for x in window) - min(x.low for x in window)
            if amp < cfg.consolidation_range_atr * atr:
                return Plan(step.index, [], ["consolidação: preço andando de lado"])
        sup = self._nearest(engine, Role.SUPPORT, c.close, step)
        res = self._nearest(engine, Role.RESISTANCE, c.close, step)
        if sup is not None and res is not None and (res.price - sup.price) < cfg.conflict_atr * atr:
            return Plan(step.index, [], ["zona de conflito: suporte e resistência espremidos"])

        armed: list[ArmedSetup] = []
        for direction in (Direction.CALL, Direction.PUT):
            setup, why = self._arm(step, engine, direction, atr)
            if setup is not None:
                armed.append(setup)
            else:
                reasons.append(f"{direction.value.upper()}: {why}")
        if len(armed) == 2:
            return Plan(step.index, [], ["CALL e PUT armados ao mesmo tempo: leitura contraditória"])
        return Plan(step.index, armed, reasons)

    # ------------------------------------------------------------------ peças

    def _usable(self, engine: LdpEngine, role: Role, step: EngineStep) -> list[Level]:
        """Marcações fortes do papel pedido, sem o fechamento da própria vela (é onde a próxima abre)."""
        out = []
        for lv in engine.levels.active(role):
            if lv.strength < self.cfg.min_strength:
                continue
            if lv.created_index == step.index and all(src.split(":")[-1] in _CLOSE_KINDS for src in lv.sources):
                continue
            out.append(lv)
        return out

    def _nearest(self, engine: LdpEngine, role: Role, price: float, step: EngineStep) -> Level | None:
        levels = self._usable(engine, role, step)
        if role is Role.SUPPORT:
            below = [lv for lv in levels if lv.price <= price]
            return max(below, key=lambda lv: lv.price, default=None)
        above = [lv for lv in levels if lv.price >= price]
        return min(above, key=lambda lv: lv.price, default=None)

    def _candidates(self, engine: LdpEngine, direction: Direction, close: float, step: EngineStep) -> list[Level]:
        role = Role.SUPPORT if direction is Direction.CALL else Role.RESISTANCE
        levels = self._usable(engine, role, step)
        if direction is Direction.CALL:
            return sorted((lv for lv in levels if lv.price <= close), key=lambda lv: -lv.price)
        return sorted((lv for lv in levels if lv.price >= close), key=lambda lv: lv.price)

    def _trigger_type(self, lv: Level, step: EngineStep, direction: Direction, atr: float) -> str:
        if lv.flipped and lv.broken_index == step.index:
            return "throwback"
        attack = step.info.direction == (-1 if direction is Direction.CALL else 1)
        if attack and lv.created_index < step.index and abs(step.info.candle.close - lv.price) <= self.cfg.trava_tol_atr * atr:
            return "reversao"
        return "retracao"

    def _arm(self, step: EngineStep, engine: LdpEngine, direction: Direction, atr: float) -> tuple[ArmedSetup | None, str]:
        cfg = self.cfg
        c = step.info.candle
        if cfg.use_lines_rule:
            lines = [v for v in (self._green_line, self._red_line) if v is not None]
            if direction is Direction.CALL and not all(c.close > v for v in lines):
                return None, "preço não está acima das duas linhas"
            if direction is Direction.PUT and not all(c.close < v for v in lines):
                return None, "preço não está abaixo das duas linhas"

        chosen: Level | None = None
        trigger = "retracao"
        for lv in self._candidates(engine, direction, c.close, step):
            dist = abs(c.close - lv.price)
            if dist > cfg.reach_atr * atr:
                break
            kind = self._trigger_type(lv, step, direction, atr)
            if dist < cfg.min_distance_atr * atr and kind != "reversao":
                continue
            chosen, trigger = lv, kind
            break
        if chosen is None:
            return None, "nenhuma marcação forte ao alcance de uma retração"

        if trigger == "retracao" and step.run_direction == (1 if direction is Direction.CALL else -1) and step.run_length >= 3:
            start = engine.candles[-step.run_length].open
            if abs(c.close - start) / step.run_length > cfg.steep_ratio * atr:
                return None, "pernada íngreme demais para retração (pág. 131)"

        confluences = {
            "gatilho": True,
            "forca": chosen.strength >= 3 or len(chosen.sources) >= 2,
            "contexto": self._context_agrees(direction, c.close),
            "espaco": self._room_ok(engine, direction, chosen, c.close, atr, step),
            "tendencia": self._trend_agrees(direction),
        }
        score = sum(confluences.values())
        if score < cfg.min_confluences:
            missing = ", ".join(CONFLUENCE_LABELS[k] for k, v in confluences.items() if not v)
            return None, f"{score} de {cfg.min_confluences} confluências (faltou: {missing})"
        return ArmedSetup(
            direction=direction,
            trigger=trigger,
            level_price=chosen.price,
            level_strength=chosen.strength,
            level_sources=list(chosen.sources),
            decision_index=step.index,
            decision_ts=c.ts,
            target_ts=c.ts + self.timeframe,
            window_seconds=cfg.window_seconds,
            touch_tol=cfg.touch_tol_atr * atr,
            prev_close=c.close,
            prev_range=c.range,
            gap_tol_pct=cfg.gap_tol_pct,
            confluences=confluences,
        ), "armado"

    def _context_agrees(self, direction: Direction, close: float) -> bool:
        """Pág. 162: acima do alinhamento da nova alta + nova posição a leitura é CALL; abaixo, PUT."""
        want = 1 if direction is Direction.CALL else -1
        for step in reversed(self._recent):
            for s in step.structures:
                if s.name == "nova_posicao":
                    if s.direction != want:
                        return False
                    mark = s.marks[0].price if s.marks else None
                    return mark is None or (close > mark if want > 0 else close < mark)
        return False

    def _room_ok(self, engine: LdpEngine, direction: Direction, lv: Level, close: float, atr: float, step: EngineStep) -> bool:
        if direction is Direction.CALL:
            barrier = self._nearest(engine, Role.RESISTANCE, close, step)
            room = None if barrier is None else barrier.price - lv.price
        else:
            barrier = self._nearest(engine, Role.SUPPORT, close, step)
            room = None if barrier is None else lv.price - barrier.price
        return room is None or room >= self.cfg.room_atr * atr

    def _trend_agrees(self, direction: Direction) -> bool:
        if self._ema_f is None or self._ema_s is None or self._ema_s_prev is None:
            return False
        if direction is Direction.CALL:
            return self._ema_f > self._ema_s and self._ema_s >= self._ema_s_prev
        return self._ema_f < self._ema_s and self._ema_s <= self._ema_s_prev


# ---------------------------------------------------------------------- execução em lote (backtest)


def run_plans(candles: Sequence[Candle], cfg: ApostilaConfig | None = None, timeframe: int = 60) -> tuple[LdpEngine, list[Plan]]:
    engine = LdpEngine()
    strat = LdpApostila(cfg, timeframe)
    plans = [strat.on_step(engine.process(c), engine) for c in candles]
    return engine, plans


def backtest(candles: Sequence[Candle], plans: Sequence[Plan], subcandles: Iterable[Candle], timeframe: int = 60) -> list[dict]:
    """Avalia os setups armados com as velas curtas da vela de entrada. Só devolve as que ENTRARAM."""
    subs = sorted(subcandles, key=lambda s: s.ts)
    keys = [s.ts for s in subs]
    out = []
    for k, plan in enumerate(plans):
        if k + 1 >= len(candles) or not plan.armed:
            continue
        nxt = candles[k + 1]
        if nxt.ts != candles[k].ts + timeframe:
            continue
        inside = subs[bisect_left(keys, nxt.ts):bisect_left(keys, nxt.ts + timeframe)]
        if not inside:
            continue
        for setup in plan.armed:
            entry, _ = simulate_entry(setup, inside)
            if entry is None:
                continue
            out.append({"setup": setup, "entry_price": entry, "exit_price": nxt.close,
                        "result": judge(setup.direction.value, entry, nxt.close)})
    return out
