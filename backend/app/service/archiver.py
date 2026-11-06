"""Guarda sozinho as velas de 1 min e de 5 s dos pares configurados e dos pares da pesquisa.

A IQ só mantém velas de 5 s por ~1 semana; guardando a cada 6 horas, a pesquisa ganha dados novos
toda semana (e o período que nenhum ajuste viu cresce para conferir as estratégias).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from app.broker.base import Broker
from app.db.database import Database
from app.research.dataset import RESEARCH_ASSETS, SUB_TF, download
from app.service.config_store import ConfigStore

log = logging.getLogger(__name__)

MAX_BACK = 8 * 86400  # até onde buscar quando o par ainda não tem nada guardado


class ResearchArchiver:
    def __init__(self, db: Database, broker_provider: Callable[[], Broker], config: ConfigStore,
                 interval: float = 6 * 3600, first_delay: float = 600,
                 extra_assets: tuple[str, ...] = RESEARCH_ASSETS) -> None:
        self.db = db
        self.extra_assets = extra_assets
        self._broker = broker_provider
        self.config = config
        self.interval, self.first_delay = interval, first_delay
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def assets(self) -> list[str]:
        return list(dict.fromkeys([*self.config.get().assets, *self.extra_assets]))

    def run_once(self) -> int:
        broker = self._broker()
        now = int(broker.server_time())
        last = {(s["asset"], s["timeframe"]): s["last_ts"] for s in self.db.candle_series()}
        total = 0
        for asset in self.assets():
            for tf in (60, SUB_TF):
                since = max(now - MAX_BACK, last.get((asset, tf), 0) - tf)
                try:
                    total += download(broker, self.db, asset, tf, since, now)
                except Exception as exc:  # noqa: BLE001 - um par com problema não para os outros
                    log.warning("Arquivo de velas %s %ss: %s", asset, tf, exc)
        log.info("Base de pesquisa: %d velas guardadas", total)
        return total

    def start(self) -> None:
        if self._thread is not None:
            return

        def loop() -> None:
            if self._stop.wait(self.first_delay):
                return
            while not self._stop.is_set():
                try:
                    self.run_once()
                except Exception as exc:  # noqa: BLE001
                    log.warning("Arquivo de velas falhou: %s", exc)
                if self._stop.wait(self.interval):
                    return

        self._thread = threading.Thread(target=loop, name="arquivo-velas", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
