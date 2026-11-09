"""Resolve sinais pendentes sem depender do bot ligado.

Enquanto o programa (servidor) estiver aberto, a cada minuto: pega os sinais pendentes cuja vela
de entrada já fechou, busca essa vela no histórico da IQ Option e grava win/loss/empate. Se o
programa estava desligado, resolve tudo assim que abrir. Se a vela não existir mais no histórico
depois de `cancel_after` segundos, o sinal vira "cancelado".
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from collections.abc import Callable

from app.broker.base import Broker
from app.db.database import Database
from app.paper import CANCELED, judge, profit_units
from app.service.events import EventHub

log = logging.getLogger(__name__)
MAX_SPAN_CANDLES = 900


class PendingResolver:
    def __init__(
        self,
        db: Database,
        broker_provider: Callable[[], Broker],
        hub: EventHub | None = None,
        interval: float = 60.0,
        grace: int = 5,
        cancel_after: int = 6 * 3600,
    ) -> None:
        self.db = db
        self._provider = broker_provider
        self.hub = hub
        self.interval = interval
        self.grace = grace
        self.cancel_after = cancel_after
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def run_once(self, now: float | None = None) -> int:
        now = time.time() if now is None else now
        due = [p for p in self.db.all_pending() if p["entry_ts"] + p["timeframe"] + self.grace <= now]
        if not due:
            return 0
        broker = self._provider()
        groups: dict[tuple[str, int], list[dict]] = defaultdict(list)
        for p in due:
            groups[(p["asset"], p["timeframe"])].append(p)
        resolved = 0
        for (asset, tf), items in groups.items():
            items.sort(key=lambda p: p["entry_ts"])
            i = 0
            while i < len(items):
                start = items[i]["entry_ts"]
                chunk = [p for p in items[i:] if p["entry_ts"] - start < MAX_SPAN_CANDLES * tf]
                end = chunk[-1]["entry_ts"] + tf
                candles = broker.get_candles(asset, tf, (end - start) // tf + 2, end_ts=end)
                by_ts = {c.ts: c for c in candles}
                for p in chunk:
                    c = by_ts.get(p["entry_ts"])
                    if c is not None:
                        entry = p["entry_price"] if p["entry_price"] is not None else c.open
                        result = judge(p["direction"], entry, c.close)
                        row = self.db.resolve_signal(p["id"], entry=entry, exit_=c.close, result=result,
                                                     profit=profit_units(result, p["payout"]))
                        if row:  # se a ordem já fechou, o resultado é o da corretora
                            resolved += 1
                            if self.hub:
                                self.hub.publish({"type": "result", "signal": row})
                    elif now - p["entry_ts"] > self.cancel_after:
                        self.db.resolve_signal(p["id"], entry=p["entry_price"], exit_=None, result=CANCELED, profit=0.0)
                i += len(chunk)
        if resolved:
            log.info("Resolvidos %d sinais pendentes pelo histórico da IQ", resolved)
        return resolved

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="resolvedor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        wait = 1.0  # primeira rodada logo ao abrir o programa
        while not self._stop.wait(wait):
            try:
                self.run_once()
                wait = self.interval
            except Exception as exc:  # noqa: BLE001 - sem conexão/login: tenta de novo mais tarde
                log.warning("Não foi possível resolver pendentes agora: %s", exc)
                wait = max(self.interval, 300.0)
