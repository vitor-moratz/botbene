"""Pesquisa · DeepLOB (E70-IQ-001): a rede do artigo DeepLOB adaptada às velas de 5 s, só para observar.

Decisão no fechamento da vela M1 k, com as 100 últimas velas de 5 s (≈ 8 min). Se a probabilidade
calibrada de subir passar do limiar, anota CALL; se a de cair passar, PUT. Entrada na vela k+1, logo no
início; vencimento no fim dela. Fora disso, não arma nada (sem lotar "Últimos setups").

- Velas de 5 s: na carga do histórico, as da IQ; ao vivo, montadas com o preço lido a cada 0,5 s.
- Pares OTC: em silêncio (no estudo, a rede não achou nada no OTC: NO_TRADE).
- Só M1. Só Observar: a configuração recusa Operar.
- Pesos e limiar em models/deeplob_iq_op.npz (treino e números em docs/estrategia.md, seção A4).
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from pathlib import Path

from app.ldp.engine import EngineStep, LdpEngine
from app.market.candle import Candle, is_otc
from app.strategies.base import Direction
from app.strategies.ldp_apostila import ArmedSetup, Plan

NAME = "deeplob_iq"
MODEL = Path(__file__).with_name("models") / "deeplob_iq_op.npz"
SUB = 5
W = 100  # velas de 5 s na janela (igual a deeplob_net.W)


class DeepLobIQ:
    name = NAME
    needs_windows = True  # precisa das velas de 5 s (carga) e da vela em formação (ao vivo)

    def __init__(self, timeframe: int = 60, model_path: Path = MODEL) -> None:
        self.timeframe = timeframe
        self.asset: str | None = None
        self._path = model_path
        self._p: dict | None = None
        self._net = None
        self._error: str | None = None
        self.bars: deque[tuple[int, float, float, float, float]] = deque(maxlen=W + 40)
        self._cur: list | None = None  # vela de 5 s em formação (ao vivo)
        self._clean_from = 0  # depois de um buraco preenchido, a janela só vale com velas reais

    def bind_asset(self, asset: str) -> None:
        self.asset = asset

    def reset(self) -> None:
        self.bars.clear()
        self._cur = None
        self._clean_from = 0

    # ------------------------------------------------------------------ velas de 5 s

    def _push(self, ts: int, o: float, h: float, l: float, c: float) -> None:
        if self.bars:
            last = self.bars[-1][0]
            if ts <= last:
                return
            if ts - last > 60:
                self.bars.clear()
                self._clean_from = 0
            else:
                pc = self.bars[-1][4]
                if ts - last > SUB:  # sem leitura no intervalo: vela parada, e a janela espera velas reais
                    for t in range(last + SUB, ts, SUB):
                        self.bars.append((t, pc, pc, pc, pc))
                    self._clean_from = ts
        self.bars.append((ts, o, h, l, c))

    def watch_window(self, target_ts: int, subs: Sequence[Candle]) -> None:
        """Carga do histórico e pesquisa: as velas de 5 s da vela `target_ts`, em ordem."""
        self._cur = None
        for s in subs:
            self._push(s.ts, s.open, s.high, s.low, s.close)

    def watch_forming(self, forming: Candle, now: float) -> None:
        """Ao vivo: monta a vela de 5 s com o preço lido a cada volta do bot."""
        slot = forming.ts + min(self.timeframe - SUB, max(0, int((now - forming.ts) // SUB) * SUB))
        price = forming.close
        cur = self._cur
        if cur is not None and cur[0] != slot:
            if cur[0] < slot:
                self._push(*cur)
            cur = self._cur = None
        if cur is None:
            o = forming.open if slot == forming.ts else price
            self._cur = [slot, o, max(o, price), min(o, price), price]
        else:
            cur[2], cur[3], cur[4] = max(cur[2], price), min(cur[3], price), price

    def _close_minute(self, k: Candle) -> None:
        """Fecha a última vela de 5 s do minuto com o fechamento oficial da vela M1."""
        last = k.ts + self.timeframe - SUB
        cur = self._cur
        if cur is not None and cur[0] <= last:
            cur[2], cur[3], cur[4] = max(cur[2], k.close), min(cur[3], k.close), k.close
            self._push(*cur)
            self._cur = None
        if self.bars and self.bars[-1][0] < last and k.ts <= self.bars[-1][0]:
            pc = self.bars[-1][4]
            self._push(last, pc, max(pc, k.close), min(pc, k.close), k.close)

    # ------------------------------------------------------------------ decisão

    def _load(self):
        if self._p is None and self._error is None:
            try:
                from app.strategies import deeplob_net  # numpy só é carregado aqui
                self._net = deeplob_net
                self._p = deeplob_net.load(self._path)
            except Exception as exc:  # noqa: BLE001 - sem numpy ou sem o arquivo: a estratégia fica parada
                self._error = f"modelo indisponível ({exc.__class__.__name__}: {exc})"
        return self._p

    def on_step(self, step: EngineStep, engine: LdpEngine) -> Plan:
        k = step.info.candle
        self._close_minute(k)
        if self.timeframe != 60:
            return Plan(step.index, [], ["só vale em velas de 1 min"])
        if self.asset and is_otc(self.asset):
            return Plan(step.index, [], ["OTC: a rede não achou nada no estudo (fica em silêncio)"])
        end = k.ts + self.timeframe - SUB
        bars = list(self.bars)
        ready = (len(bars) >= W + 1 and bars[-1][0] == end and bars[-W - 1][0] == end - W * SUB
                 and bars[-W - 1][0] >= self._clean_from)
        if not ready:
            n = sum(1 for b in bars if b[0] >= max(self._clean_from, end - W * SUB)) if bars and bars[-1][0] == end else 0
            return Plan(step.index, [], [f"aquecendo: {min(n, W + 1)} de {W + 1} velas de 5 s"])
        p = self._load()
        if p is None:
            return Plan(step.index, [], [self._error or "modelo indisponível"])
        prob = self._net.probability(p, self._net.window_features(bars[-W - 1:]))
        thr = float(p["threshold"])
        if prob >= thr:
            direction = Direction.CALL
        elif prob <= 1 - thr:
            direction = Direction.PUT
        else:
            return Plan(step.index, [], [f"probabilidade de subir {prob:.3f}: sem entrada (limiar {thr:.2f})"])
        chance = prob if direction is Direction.CALL else 1 - prob
        setup = ArmedSetup(
            direction=direction,
            trigger="deeplob",
            level_price=k.close,  # entra logo no início da vela seguinte, no preço do momento
            level_strength=0,
            level_sources=[f"probabilidade {chance:.2f} de {'subir' if direction is Direction.CALL else 'cair'}"],
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
        )
        return Plan(step.index, [setup], [])
