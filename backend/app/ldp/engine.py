"""Motor incremental da apostila: recebe uma vela fechada por vez e atualiza tudo.

Cada chamada de `process()` usa só a vela nova e o passado. Por isso rodar vela a vela
(ao vivo) ou de uma vez (histórico) dá exatamente o mesmo resultado (sem repintura).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from app.ldp.candles import CandleClass, CandleInfo, classify
from app.ldp.config import LdpConfig
from app.ldp.levels import Level, LevelChange, LevelMap
from app.ldp.structures import (
    Mark,
    Structure,
    candle_marks,
    indecisao,
    nova_alta_baixa,
    nova_posicao_marks,
    taxa_dividida,
    td_topo_fundo,
)
from app.market.candle import Candle

_INDECISION = ("dupla_posicao", "futuro_alta", "futuro_baixa", "tripla_posicao")


@dataclass
class EngineStep:
    index: int
    info: CandleInfo
    structures: list[Structure] = field(default_factory=list)
    new_levels: list[Level] = field(default_factory=list)
    level_changes: list[LevelChange] = field(default_factory=list)
    atr: float | None = None
    run_direction: int = 0  # cor da sequência atual (micro-lote, pág. 125)
    run_length: int = 0

    def has(self, name: str) -> bool:
        return any(s.name == name for s in self.structures)


class LdpEngine:
    def __init__(self, cfg: LdpConfig | None = None) -> None:
        self.cfg = cfg or LdpConfig()
        self.candles: list[Candle] = []
        self.infos: list[CandleInfo] = []
        self.levels = LevelMap(self.cfg)
        self._trs: list[float] = []
        self._atr: float | None = None
        self._prev_structures: list[Structure] = []
        self._run_direction = 0
        self._run_length = 0

    def run(self, candles: Iterable[Candle]) -> list[EngineStep]:
        return [self.process(c) for c in candles]

    def process(self, candle: Candle) -> EngineStep:
        cfg = self.cfg
        index = len(self.candles)
        prev_candles = self.candles[-max(cfg.breakout_window, cfg.extreme_lookback) :]
        info = classify(candle, index, prev_candles, cfg)
        self.candles.append(candle)
        self.infos.append(info)
        atr = self._update_atr(candle)
        self._update_run(info)

        # 1) A vela nova testa as marcações que já existiam.
        changes = self.levels.apply_candle(info)

        # 2) Estruturas que ficaram conhecidas com esta vela.
        structures = candle_marks(info, cfg)
        structures += nova_alta_baixa(info, prev_candles, cfg)
        if len(self.infos) >= 2:
            a = self.infos[-2]
            structures += taxa_dividida(a, info)
            structures += td_topo_fundo(a, info, self.candles, cfg)
            ind = indecisao(a, info)
            if ind and len(self.infos) >= 3 and indecisao(self.infos[-3], a):
                prev_side = indecisao(self.infos[-3], a)[0].detail
                if prev_side == ind[0].detail:
                    ind = [Structure("tripla_posicao", ind[0].index, self.infos[-3].index, 0, ind[0].marks, 111, ind[0].detail)]
            structures += ind
        structures += self._nova_posicao(info)
        structures += self._lotes_e_defesas()

        # 3) Marcações dessas estruturas viram níveis (ou reforçam níveis próximos).
        new_levels: list[Level] = []
        for s in structures:
            new_levels += self.levels.add_structure(s, info, atr)
        changes += self.levels.expire(index)

        self._prev_structures = structures
        return EngineStep(
            index=index,
            info=info,
            structures=structures,
            new_levels=new_levels,
            level_changes=changes,
            atr=atr,
            run_direction=self._run_direction,
            run_length=self._run_length,
        )

    # ------------------------------------------------------------------ helpers

    def _update_atr(self, candle: Candle) -> float | None:
        if self.candles[:-1]:
            pc = self.candles[-2].close
            tr = max(candle.high - candle.low, abs(candle.high - pc), abs(candle.low - pc))
        else:
            tr = candle.high - candle.low
        p = self.cfg.atr_period
        self._trs.append(tr)
        if len(self._trs) < p:
            self._atr = sum(self._trs) / len(self._trs)
        elif len(self._trs) == p:
            self._atr = sum(self._trs) / p
        else:
            assert self._atr is not None
            self._atr = (self._atr * (p - 1) + tr) / p
        return self._atr

    def _update_run(self, info: CandleInfo) -> None:
        if info.direction == 0:
            return  # doji não quebra nem estende a sequência de cores
        if info.direction == self._run_direction:
            self._run_length += 1
        else:
            self._run_direction, self._run_length = info.direction, 1

    def _nova_posicao(self, info: CandleInfo) -> list[Structure]:
        """Nova posição (pág. 113-120): a vela que confirma o movimento novo.

        - Logo após uma nova alta/baixa, se continuar o movimento.
        - A vela que rompe uma indecisão/dupla/tripla posição (pág. 108, 115 e).
        """
        if len(self.infos) < 2:
            return []
        prev = self.infos[-2]
        c = info.candle
        out: list[Structure] = []
        for s in self._prev_structures:
            if s.name == "nova_alta" and c.close > prev.candle.close:
                out.append(Structure("nova_posicao", info.index, info.index, 1, nova_posicao_marks(info, 1), 113, "apos_nova_alta"))
            elif s.name == "nova_baixa" and c.close < prev.candle.close:
                out.append(Structure("nova_posicao", info.index, info.index, -1, nova_posicao_marks(info, -1), 113, "apos_nova_baixa"))
            elif s.name in _INDECISION:
                group = self.candles[s.ref_index : info.index]
                top, bottom = max(x.high for x in group), min(x.low for x in group)
                if c.close > top:
                    out.append(Structure("nova_posicao", info.index, info.index, 1, nova_posicao_marks(info, 1), 115, "rompeu_indecisao"))
                elif c.close < bottom:
                    out.append(Structure("nova_posicao", info.index, info.index, -1, nova_posicao_marks(info, -1), 115, "rompeu_indecisao"))
        return out[:1]

    def _lotes_e_defesas(self) -> list[Structure]:
        """Nano-lote (pág. 126, 130) e defesa do 1º candle da reversão confirmada (pág. 149-151)."""
        out: list[Structure] = []
        dirs = [i.direction for i in self.infos[-4:]]
        if len(dirs) == 4:
            x, y = dirs[0], dirs[2]
            if x != 0 and dirs[1] == x and y == -x and dirs[3] == x:
                nano = self.infos[-2]
                c = nano.candle
                marks = (Mark(c.body_top, "corpo_topo", 2), Mark(c.body_bottom, "corpo_base", 2))
                out.append(Structure("nano_lote", self.infos[-1].index, nano.index, x, marks, 130))
        if len(dirs) >= 3:
            x, y1, y2 = dirs[-3], dirs[-2], dirs[-1]
            if x != 0 and y1 == -x and y2 == y1:
                first = self.infos[-2]
                c = first.candle
                marks_l = [Mark(c.open, "defesa_abertura", 3), Mark(c.close, "defesa_fechamento", 2)]
                if first.cls is CandleClass.FORCA:
                    marks_l.append(Mark(c.mid, "50%", 1))
                out.append(Structure("defesa", self.infos[-1].index, first.index, y1, tuple(marks_l), 151))
        return out
