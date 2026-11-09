"""Grava o sentimento dos traders da IQ (a fração que a IQ mostra comprando e vendendo) a cada 5 s, na base de pesquisa.

Plano de 09/11/2026, frente F1: no OTC, o preço não tem memória e cada par é um gerador separado, então o
sentimento é a única informação que não é o próprio preço. Fica junto das velas de 5 s e no mesmo relógio:
o valor gravado em `ts` é o que a IQ tinha mandado até aquele instante. `age` diz há quanto tempo ele chegou,
para o estudo separar valor parado de valor novo.

Só usa a conexão que o bot já tem aberta (nunca faz login por conta própria).
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from app.broker.base import Broker, BrokerError
from app.db.database import Database
from app.research.dataset import RESEARCH_ASSETS
from app.service.config_store import ConfigStore

log = logging.getLogger(__name__)

STEP = 5  # segundos, o mesmo das velas curtas da pesquisa
FLUSH_SECONDS = 60  # grava no banco em lotes
RESUBSCRIBE_AGE = 300  # sem atualização há isso: pede de novo (a assinatura pode ter caído sem aviso)
MAX_AGE = 900  # valor parado há mais que isso não é gravado (par fechado ou assinatura morta)


class MoodRecorder:
    def __init__(self, db: Database, broker_provider: Callable[[], Broker | None], config: ConfigStore,
                 extra_assets: tuple[str, ...] = RESEARCH_ASSETS, step: int = STEP,
                 flush_seconds: float = FLUSH_SECONDS, first_delay: float = 30.0) -> None:
        self.db = db
        self._broker = broker_provider
        self.config = config
        self.extra_assets = extra_assets
        self.step, self.flush_seconds, self.first_delay = step, flush_seconds, first_delay
        self._buffer: list[tuple[str, int, float, float]] = []
        self._buffer_lock = threading.Lock()
        self._last_flush = time.monotonic()
        self._resub_at: dict[str, float] = {}
        self._next_delay = float(step)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.saved = 0

    def assets(self) -> list[str]:
        return list(dict.fromkeys([*self.config.get().assets, *self.extra_assets]))

    def sample(self, broker: Broker, ts: int) -> int:
        """Uma amostra de cada par no instante `ts`. Devolve quantos pares tinham valor."""
        rows = []
        now = time.monotonic()
        for asset in self.assets():
            try:
                if not broker.subscribe_mood(asset):
                    continue
                got = broker.traders_mood(asset)
                if got is not None and got[1] > RESUBSCRIBE_AGE and now - self._resub_at.get(asset, -1e9) > RESUBSCRIBE_AGE:
                    self._resub_at[asset] = now
                    broker.subscribe_mood(asset, force=True)
            except BrokerError as exc:  # um par com problema não para os outros
                log.debug("Sentimento %s: %s", asset, exc)
                continue
            if got is None or got[1] > MAX_AGE:
                continue
            rows.append((asset, ts, got[0], round(got[1], 1)))
        with self._buffer_lock:
            self._buffer.extend(rows)
        return len(rows)

    def flush(self) -> int:
        with self._buffer_lock:
            rows, self._buffer = self._buffer, []
        self._last_flush = time.monotonic()
        if rows:
            self.db.save_mood(rows)
            self.saved += len(rows)
        return len(rows)

    def run_once(self) -> int:
        broker = self._broker()
        if broker is None or not broker.is_connected():  # bot sem conexão agora: tenta na próxima
            self._next_delay = float(self.step)
            return 0
        now = broker.server_time()
        n = self.sample(broker, int(now) - int(now) % self.step)
        if time.monotonic() - self._last_flush >= self.flush_seconds:
            self.flush()
        # acorda logo depois da próxima marca de 5 s do relógio da IQ
        self._next_delay = self.step - (broker.server_time() % self.step) + 0.25
        return n

    def start(self) -> None:
        if self._thread is not None:
            return

        def loop() -> None:
            if self._stop.wait(self.first_delay):
                return
            warned = 0.0
            while not self._stop.is_set():
                try:
                    self.run_once()
                except Exception as exc:  # noqa: BLE001 - o gravador nunca derruba o servidor
                    self._next_delay = float(self.step)
                    if time.monotonic() - warned > 600:
                        warned = time.monotonic()
                        log.warning("Gravador de sentimento: %s", exc)
                if self._stop.wait(self._next_delay):
                    break
            try:
                self.flush()
            except Exception as exc:  # noqa: BLE001
                log.warning("Sentimento não gravado ao parar: %s", exc)

        self._thread = threading.Thread(target=loop, name="sentimento", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
