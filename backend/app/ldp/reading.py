"""Leitura do gráfico como o estudo ensina: lotes, nova alta/baixa + nova posição, indecisão e regiões.

Só lê: não decide entrada, não grava nada e não manda ordem. Recebe uma vela fechada por vez e usa só
o passado, então ao vivo e no histórico dá o mesmo resultado.

"Identifique um lote passado. Dentro desse lote localize e marque a nova alta / nova baixa + nova
posição. Pronto, sua região de defesa está marcada." (pág. 162)

Lote (pág. 121-133)
- Velas da mesma cor. Abre por reversão, por comando ou depois de um fechamento de preço.
- Fecha pela reversão, por um fim de taxa ou pelo rompimento: o corpo passa da vela que abriu o lote (pág. 115).
- Uma vela de outra cor seguida da cor do lote é nano-lote (pág. 126): não fecha o lote (pág. 182).

Região = onde o preço volta para ser defendido, com o lado da leitura. Só entram as do lote recente e
das estruturas que o estudo manda marcar, em vez de todas as marcações do mapa (LevelMap).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.ldp.candles import CandleClass as K
from app.ldp.engine import EngineStep, LdpEngine
from app.market.candle import Candle

MOVEMENT_SCENARIOS = ("topos_fundos", "tendencia", "consolidacao")  # os 3 movimentos da pág. 223

_TD = {  # estrutura -> (código, nome, página); a marcação é a junção das duas velas
    "td_n1": ("TD1", "Taxa dividida N1", 41), "td_n2": ("TD2", "Taxa dividida N2", 41),
    "td_n3": ("TD3", "Taxa dividida N3", 42), "td_intermediaria": ("TDI", "Taxa dividida intermediária", 43),
    "td_forte": ("TD", "Taxa dividida forte", 37), "divisao_preco": ("DV", "Divisão de preço", 54),
    "td_topo_n1": ("TDT", "Taxa dividida de topo N1", 52), "td_topo_n2": ("TDT", "Taxa dividida de topo N2", 53),
    "td_fundo_n1": ("TDF", "Taxa dividida de fundo N1", 52), "td_fundo_n2": ("TDF", "Taxa dividida de fundo N2", 53),
}
_JUNCTION = ("taxa_dividida", "divisao_preco")
_INDECISION = {  # estrutura -> (código, nome, página)
    "dupla_posicao": ("DP", "Dupla posição", 109), "tripla_posicao": ("TP", "Tripla posição", 111),
    "futuro_alta": ("FA", "Futuro de alta", 108), "futuro_baixa": ("FB", "Futuro de baixa", 108),
}
_ALWAYS_KEPT = ("NA", "NB", "DP", "TP", "FA", "FB")  # a região central do estudo (pág. 162) e a defesa forte da indecisão (pág. 110)
_DEFENSE_NAMES = {  # como cada região aparece quando uma vela de força para nela
    "NA": "primeiro registro + nova posição", "NB": "primeiro registro + nova posição",
    "C1": "comando", "C2": "comando", "TD": "taxa dividida", "TD1": "taxa dividida", "TD2": "taxa dividida",
    "TD3": "taxa dividida", "TDI": "taxa dividida", "TDT": "taxa dividida de topo", "TDF": "taxa dividida de fundo",
    "DV": "divisão de preço", "DP": "dupla posição", "TP": "tripla posição", "FA": "futuro de alta", "FB": "futuro de baixa",
    "NL": "nano-lote", "VF": "vela de força", "DF": "1º candle da reversão",
}


@dataclass(frozen=True)
class ReadingConfig:
    keep_lots_per_side: int = 2  # regiões dos últimos lotes de cada lado; as mais velhas saem da leitura
    max_other_per_lot: int = 2  # além de nova alta/baixa + nova posição e indecisão, em cada lote
    max_active_regions: int = 12
    region_max_age: int = 120  # velas
    symmetry_lookback: int = 10  # transferência e desinstalação: pavios alinhados nestas últimas velas
    symmetry_tol_atr: float = 0.05
    scenario_window: int = 30
    consolidation_window: int = 10
    consolidation_range: float = 2.5  # amplitude das últimas velas menor que isto × vela média = consolidado
    trend_efficiency: float = 0.5  # deslocamento ÷ caminho percorrido, de 0 a 1
    trend_move: float = 4.0  # deslocamento mínimo, em velas médias
    average_window: int = 120
    # Vela de força é de impulso (pág. 11): maior que a vela média recente e com corpo de verdade.
    force_range: float = 1.2  # amplitude ≥ isto × média das 14 velas anteriores
    force_body: float = 0.5  # corpo ≥ isto × amplitude
    # Defesa nasce em topos e fundos (pág. 149): o 1º candle da reversão no extremo das últimas N velas.
    extreme_window: int = 10
    lock_tol_atr: float = 0.15  # fechou "travado" na região: a até isto × ATR da borda


@dataclass
class Lot:
    id: int
    direction: int  # +1 compra, -1 venda
    start: int
    end: int
    open_cause: str  # reversao | comando | fim_de_taxa | rompimento
    close_cause: str | None = None  # reversao | fim_de_taxa | rompimento
    closed_at: int | None = None
    broke_reference: bool = False  # alguma vela do lote já fechou além da máxima/mínima anterior a ele
    nova: int | None = None  # vela da nova alta/baixa
    nova_posicao: int | None = None
    scanned: int = -1


@dataclass
class Region:
    id: int
    low: float
    high: float
    side: int  # +1 = buscou é CALL · -1 = buscou é PUT · 0 = indecisão, ainda sem lado
    code: str
    label: str
    page: int
    lot_id: int | None
    created: int
    resolved: int | None = None  # vela que rompeu a indecisão e definiu o lado
    broken: int | None = None
    expired: int | None = None

    @property
    def active(self) -> bool:
        return self.broken is None and self.expired is None


@dataclass(frozen=True)
class Tag:
    index: int  # vela que recebe o rótulo
    confirmed: int  # vela em que ficou conhecido
    code: str
    label: str
    page: int
    direction: int = 0
    detail: str = ""


@dataclass
class ReadingEngine:
    cfg: ReadingConfig = field(default_factory=ReadingConfig)
    lots: list[Lot] = field(default_factory=list)
    regions: list[Region] = field(default_factory=list)
    tags: list[Tag] = field(default_factory=list)
    scenarios: list[str | None] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._lot: Lot | None = None
        self._candidate: int | None = None  # 1ª vela de outra cor, esperando a seguinte para saber o que é
        self._next_cause = "reversao"
        self.defense_hits: list[Region] = []  # regiões em que a vela de força desta vela travou
        self.last_index = -1

    @property
    def current_lot(self) -> Lot | None:
        return self._lot

    def active_regions(self) -> list[Region]:
        return [r for r in self.regions if r.active]

    def impulse(self, engine: LdpEngine, i: int) -> bool:
        """Vela de força de verdade: pavio na abertura (classe da apostila) e maior que o normal (pág. 11)."""
        info = engine.infos[i]
        if info.cls is not K.FORCA:
            return False
        before = engine.candles[max(0, i - 14):i]
        if len(before) < 5:
            return False
        average = sum(c.range for c in before) / len(before)
        c = info.candle
        return average > 0 and c.range >= self.cfg.force_range * average and c.body >= self.cfg.force_body * c.range

    def at_extreme(self, engine: LdpEngine, i: int, side: int) -> bool:
        """A vela i está num topo (side < 0) ou num fundo (side > 0) das últimas velas."""
        window = engine.candles[max(0, i - self.cfg.extreme_window):i + 1]
        c = engine.candles[i]
        return c.high >= max(x.high for x in window) if side < 0 else c.low <= min(x.low for x in window)

    def process(self, step: EngineStep, engine: LdpEngine) -> None:
        self.last_index = step.index
        self._force_at_defense(step, engine)
        self._test_regions(step)
        self._update_lots(step, engine)
        self._add_structures(step, engine)
        self._symmetry(step, engine)
        self._expire(step.index)
        self.scenarios.append(self._scenario(engine))

    # ------------------------------------------------------------------ lotes

    def _update_lots(self, step: EngineStep, engine: LdpEngine) -> None:
        i, info = step.index, step.info
        d = info.direction
        lot = self._lot
        if d == 0:  # doji não abre nem fecha lote
            if lot is not None and self._candidate is None:
                lot.end = i
            return
        if lot is None:
            if self._candidate is not None and engine.infos[self._candidate].direction == d:
                self._open_lot(self._candidate, i, d, engine)
                self._candidate = None
                self._scan_nova(self._lot, engine)
                if info.cls is K.C3:
                    self._close_lot(self._lot, "fim_de_taxa", i)
                    self._next_cause = "fim_de_taxa"
            else:
                self._candidate = i
            return
        if d == lot.direction:
            if self._candidate is not None:  # a vela de outra cor ficou sozinha e o fluxo seguiu
                self._nano_lote(self._candidate, i, lot, engine)
                self._candidate = None
            lot.end = i
            self._scan_nova(lot, engine)
            if info.cls is K.C3:  # fim de taxa fecha o lote (pág. 123); se o fluxo seguir, abre outro (pág. 122)
                self._close_lot(lot, "fim_de_taxa", i)
                self._next_cause = "fim_de_taxa"
            return
        if self._candidate is None:
            opener = engine.candles[lot.start]
            broke = info.candle.close < opener.open if lot.direction > 0 else info.candle.close > opener.open
            if broke:  # o corpo passou da vela que abriu o lote (pág. 115)
                self._close_lot(lot, "rompimento", i)
                self._next_cause = "rompimento"
            self._candidate = i
            return
        start = self._candidate  # 2ª vela seguida da outra cor: a reversão se confirmou (pág. 121, 123)
        self._close_lot(lot, "reversao", i)
        self._open_lot(start, i, d, engine, cause="reversao")
        self._candidate = None
        self._scan_nova(self._lot, engine)

    def _open_lot(self, start: int, i: int, direction: int, engine: LdpEngine, cause: str | None = None) -> None:
        if cause is None:
            cause = "comando" if engine.infos[start].cls in (K.C1, K.C2) else self._next_cause
        self._lot = Lot(id=len(self.lots) + 1, direction=direction, start=start, end=i, open_cause=cause)
        self.lots.append(self._lot)
        self._next_cause = "reversao"
        self._retire_old_lots(i)

    def _close_lot(self, lot: Lot, cause: str, i: int) -> None:
        lot.close_cause, lot.closed_at = cause, i
        self._lot = None

    def _retire_old_lots(self, i: int) -> None:
        """Só as regiões dos lotes mais recentes de cada lado continuam na leitura."""
        keep: set[int] = set()
        for side in (1, -1):
            keep |= {lot.id for lot in [x for x in self.lots if x.direction == side][-self.cfg.keep_lots_per_side:]}
        for r in self.active_regions():
            if r.lot_id is not None and r.lot_id not in keep:
                r.expired = i

    def _nano_lote(self, k: int, i: int, lot: Lot, engine: LdpEngine) -> None:
        c = engine.candles[k]
        self._tag(k, i, "NL", "Nano-lote", 126, lot.direction)
        self._region(c.body_bottom, c.body_top, lot.direction, "NL", "Nano-lote", 130, lot.id, i)

    # ------------------------------------------------------------------ nova alta/baixa + nova posição

    def _scan_nova(self, lot: Lot | None, engine: LdpEngine) -> None:
        """Rompeu a máxima/mínima anterior ao lote: o 1º pavio depois disso é a nova alta/baixa (pág. 97, 102, 129)."""
        if lot is None or lot.start == 0:
            return
        before = engine.candles[lot.start - 1]
        reference = before.high if lot.direction > 0 else before.low
        for k in range(max(lot.scanned + 1, lot.start), lot.end + 1):
            lot.scanned = k
            info = engine.infos[k]
            if info.direction != lot.direction:
                continue
            c = info.candle
            if lot.nova is not None:
                if lot.nova_posicao is None:
                    self._nova_posicao(lot, k, engine)
                continue
            if not lot.broke_reference:
                lot.broke_reference = c.close > reference if lot.direction > 0 else c.close < reference
            if lot.broke_reference and (info.has_upper_wick if lot.direction > 0 else info.has_lower_wick):
                lot.nova = k
                self._nova(lot, k, c)

    def _nova(self, lot: Lot, k: int, c: Candle) -> None:
        up = lot.direction > 0
        name = "Nova alta" if up else "Nova baixa"
        self._tag(k, lot.end, "NA" if up else "NB", name, 96, lot.direction)
        # pavio + fechamento (pág. 102); a projeção da vela seguinte completa a faixa
        low, high = (c.close, c.high) if up else (c.low, c.close)
        self._region(low, high, lot.direction, "NA" if up else "NB", name, 102, lot.id, lot.end)

    def _nova_posicao(self, lot: Lot, k: int, engine: LdpEngine) -> None:
        lot.nova_posicao = k
        up = lot.direction > 0
        info = engine.infos[k]
        c = info.candle
        self._tag(k, lot.end, "NP", "Nova posição", 113, lot.direction)
        # Projeção da nova posição; sem esse pavio (comando único), a abertura dela (pág. 129-130).
        if up:
            mark = c.low if info.has_lower_wick else c.open
        else:
            mark = c.high if info.has_upper_wick else c.open
        region = next((r for r in reversed(self.regions) if r.lot_id == lot.id and r.code in ("NA", "NB")), None)
        if region is None or not region.active:
            return
        if up:
            region.low = min(region.low, mark)
        else:
            region.high = max(region.high, mark)
        region.label = ("Nova alta" if up else "Nova baixa") + " + nova posição"

    # ------------------------------------------------------------------ outras estruturas

    def _add_structures(self, step: EngineStep, engine: LdpEngine) -> None:
        i = step.index
        lot_id = self._lot.id if self._lot is not None else None
        for s in step.structures:
            if s.name in _TD:
                code, label, page = _TD[s.name]
                self._tag(s.ref_index, i, code, label, page, s.direction)
                prices = [m.price for m in s.marks if m.kind in _JUNCTION]
                if prices:
                    self._region(prices[0], prices[0], s.direction, code, label, page, lot_id, i)
            elif s.name in _INDECISION:
                code, label, page = _INDECISION[s.name]
                self._tag(i, i, code, label, page, 0, s.detail)
                prices = [m.price for m in s.marks]
                if prices:  # pavios + fracionamento: defesa forte quando o preço voltar (pág. 110, 112)
                    self._region(min(prices), max(prices), 0, code, label, page + 1, lot_id, i)
            elif s.name in ("comando_n1", "comando_unico") and s.detail in ("reversao", "rompimento"):
                code, label = ("C1", "Comando nível 1") if s.name == "comando_n1" else ("C2", "Comando único")
                self._tag(i, i, code, label, 24, s.direction, s.detail)
                c = step.info.candle
                self._region(min(c.open, c.mid), max(c.open, c.mid), s.direction, code, label, 26, lot_id, i)
            elif s.name == "expirado":
                self._tag(i, i, "C3", "Expirado / fim de taxa", 23, s.direction)
            elif s.name == "vela_de_forca" and self.impulse(engine, i):
                self._tag(i, i, "VF", "Vela de força", 11, s.direction)
                c = step.info.candle  # abertura, 50% e fechamento (pág. 138): rompeu, terminou dentro ou retraiu na VF (pág. 69-70)
                self._region(c.body_bottom, c.body_top, s.direction, "VF", "Vela de força", 138, lot_id, i)
            elif s.name == "defesa" and self.at_extreme(engine, s.ref_index - 1, s.direction):
                # 1º candle da reversão que nasceu num topo ou fundo (pág. 149): a vela antes dele é o extremo
                self._tag(s.ref_index, i, "DF", "Defesa · 1º candle da reversão", 151, s.direction)
                prices = [m.price for m in s.marks]
                if prices:
                    self._region(min(prices), max(prices), s.direction, "DF", "Defesa · 1º candle da reversão", 151, lot_id, i)

    def _force_at_defense(self, step: EngineStep, engine: LdpEngine) -> None:
        """Vela de força que foi até uma defesa e fechou nela sem romper (pág. 153, 211, 218): "ante essa negativa
        de seguimento do movimento" a leitura vira para o outro lado. Guarda as regiões em `defense_hits`."""
        self.defense_hits = []
        info = step.info
        if not step.atr or not self.impulse(engine, step.index):
            return
        tol, c, d, i = self.cfg.lock_tol_atr * step.atr, info.candle, info.direction, step.index
        for r in self.active_regions():
            if r.created >= i or r.side != -d:
                continue
            if d > 0:  # subindo contra uma região de venda: veio de baixo e fechou nela, sem passar
                reached = c.open < r.low and r.low - tol <= c.close <= r.high
            else:  # descendo contra uma região de compra: veio de cima e fechou nela, sem passar
                reached = c.open > r.high and r.low <= c.close <= r.high + tol
            if reached:
                self.defense_hits.append(r)
        if self.defense_hits:
            names = ", ".join(dict.fromkeys(_DEFENSE_NAMES.get(r.code, r.label) for r in self.defense_hits))
            self._tag(i, i, "VD", "Vela de força na defesa", 218, -d, names)

    def _symmetry(self, step: EngineStep, engine: LdpEngine) -> None:
        """Pavio alinhado com um pavio recente, sem nada passar entre eles: mesma cor é transferência de
        preço (pág. 134), cor diferente é desinstalação (pág. 135). Em cima, tende a cair; embaixo, a subir."""
        atr, info = step.atr, step.info
        if not atr or info.direction == 0:
            return
        tol = self.cfg.symmetry_tol_atr * atr
        i, c = step.index, info.candle
        for side, has, tip in ((-1, info.has_upper_wick, c.high), (1, info.has_lower_wick, c.low)):
            if not has:
                continue
            for j in range(i - 1, max(-1, i - 1 - self.cfg.symmetry_lookback), -1):
                other = engine.infos[j]
                price = other.candle.high if side < 0 else other.candle.low
                passed = price > tip + tol if side < 0 else price < tip - tol
                if passed:
                    break  # outro pavio passou: não há alinhamento com os de antes dele
                aligned = abs(price - tip) <= tol and (other.has_upper_wick if side < 0 else other.has_lower_wick)
                if aligned and other.direction != 0 and j < i - 1:
                    code, label, page = (("TR", "Transferência de preço", 134) if other.direction == info.direction
                                         else ("DS", "Desinstalação", 135))
                    self._tag(i, i, code, label, page, side, f"alinhado com a vela {i - j} atrás")
                    break

    # ------------------------------------------------------------------ regiões

    def _test_regions(self, step: EngineStep) -> None:
        """O rompimento só vale com o corpo (pág. 115). Indecisão rompida ganha o lado de quem rompeu (pág. 106-110)."""
        i, close = step.index, step.info.candle.close
        for r in self.active_regions():
            if r.created >= i:
                continue
            if r.side == 0:
                if close > r.high or close < r.low:
                    r.side, r.resolved = (1 if close > r.high else -1), i
            elif (r.side > 0 and close < r.low) or (r.side < 0 and close > r.high):
                r.broken = i

    def _region(self, low: float, high: float, side: int, code: str, label: str, page: int, lot_id: int | None, i: int) -> None:
        self.regions.append(Region(len(self.regions) + 1, low, high, side, code, label, page, lot_id, i))
        if lot_id is None or code in _ALWAYS_KEPT:
            return
        # Num lote longo, cada comando, taxa dividida e nano-lote deixaria uma região: ficam só as mais recentes.
        others = [r for r in self.active_regions() if r.lot_id == lot_id and r.code not in _ALWAYS_KEPT]
        for r in others[:-self.cfg.max_other_per_lot]:
            r.expired = i

    def _expire(self, i: int) -> None:
        active = self.active_regions()
        for r in active:
            if i - r.created > self.cfg.region_max_age:
                r.expired = i
        active = self.active_regions()
        for r in active[:max(0, len(active) - self.cfg.max_active_regions)]:
            r.expired = i
        if len(self.regions) > 2000:  # histórico curto: as encerradas só servem para desenhar o passado recente
            keep = [r for r in self.regions if r.active or (r.broken or r.expired or 0) > i - 600]
            self.regions[:] = keep

    def _tag(self, index: int, confirmed: int, code: str, label: str, page: int, direction: int = 0, detail: str = "") -> None:
        self.tags.append(Tag(index, confirmed, code, label, page, direction, detail))

    # ------------------------------------------------------------------ cenário

    def _scenario(self, engine: LdpEngine) -> str | None:
        """Topos e fundos é o melhor para a lógica do preço; tendência é para operar fluxo; consolidado, não operar (pág. 223)."""
        cfg = self.cfg
        cs = engine.candles
        if len(cs) < cfg.scenario_window + 1:
            return None
        recent = cs[-cfg.average_window:]
        average = sum(c.range for c in recent) / len(recent)
        if average <= 0:
            return None
        short = cs[-cfg.consolidation_window:]
        if max(c.high for c in short) - min(c.low for c in short) < cfg.consolidation_range * average:
            return "consolidacao"
        window = cs[-cfg.scenario_window - 1:]
        path = sum(abs(b.close - a.close) for a, b in zip(window, window[1:]))
        move = abs(window[-1].close - window[0].close)
        if path > 0 and move / path >= cfg.trend_efficiency and move >= cfg.trend_move * average:
            return "tendencia"
        return "topos_fundos"


def reading_for(engine: LdpEngine, step: EngineStep) -> ReadingEngine:
    """A leitura que acompanha este motor, atualizada até `step`. Várias estratégias no mesmo par
    usam a mesma leitura, processada uma vez por vela."""
    reading = getattr(engine, "study_reading", None)
    if reading is None:
        reading = engine.study_reading = ReadingEngine()
    if reading.last_index < step.index:
        reading.process(step, engine)
    return reading


def read_candles(candles: list[Candle], cfg: ReadingConfig | None = None) -> tuple[LdpEngine, ReadingEngine]:
    engine = LdpEngine()
    reading = ReadingEngine(cfg or ReadingConfig())
    for c in candles:
        reading.process(engine.process(c), engine)
    return engine, reading
