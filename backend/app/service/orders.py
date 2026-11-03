"""Ordens na conta demo: passa pela gestão de risco, envia, espera o vencimento e grava o resultado.

Cada ordem roda numa thread própria (enviar leva ~1 s e o resultado só sai no fim do minuto),
para não travar a leitura do mercado.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from app.broker.base import Broker, BrokerError
from app.db.database import Database
from app.paper import LOSS
from app.risk import RiskConfig, RiskManager
from app.service.events import EventHub

log = logging.getLogger(__name__)

RESULT_TIMEOUT = 90  # segundos depois do vencimento sem resultado = "sem_resultado"


class OrderManager:
    def __init__(
        self,
        db: Database,
        hub: EventHub,
        broker_provider: Callable[[], Broker],
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], float] = time.time,
        threaded: bool = True,
    ) -> None:
        self.db, self.hub = db, hub
        self._broker = broker_provider
        self._sleep, self._now = sleep, now
        self._threaded = threaded
        self._lock = threading.Lock()
        self.risk = RiskManager()

    def reset(self, cfg: RiskConfig) -> None:
        with self._lock:
            self.risk = RiskManager(cfg)

    def set_config(self, cfg: RiskConfig) -> None:
        """Muda valor/stops no meio da sessão sem zerar o placar."""
        with self._lock:
            self.risk.cfg = cfg

    def snapshot(self, payout: float = 0.85) -> dict:
        with self._lock:
            return self.risk.snapshot(payout)

    def submit(self, *, asset: str, timeframe: int, strategy: str, direction: str, ref_price: float | None,
               signal_id: int | None, payout: float = 0.85) -> dict:
        base = {"asset": asset, "timeframe": timeframe, "strategy": strategy, "direction": direction,
                "ref_price": ref_price, "signal_id": signal_id}
        with self._lock:
            ok, why = self.risk.check(payout)
            amount = self.risk.next_stake(payout)
            base["gale"] = self.risk.gale_level if self.risk.cfg.martingale else 0
            if ok:
                self.risk.opened(amount)
        if not ok:
            row = self.db.add_order(**base, amount=amount, status="bloqueada", error=why)
            self._publish(row)
            return row
        row = self.db.add_order(**base, amount=amount, status="enviando")
        self._publish(row)
        if self._threaded:
            threading.Thread(target=self._run, args=(row,), name=f"ordem-{row['id']}", daemon=True).start()
        else:
            self._run(row)
        return row

    def _run(self, row: dict) -> None:
        try:
            broker = self._broker()
            ticket = broker.buy(row["asset"], row["direction"], row["amount"])
        except Exception as exc:  # noqa: BLE001 - qualquer falha vira "erro" na ordem
            log.warning("Ordem %s não enviada: %s", row["id"], exc)
            with self._lock:
                self.risk.cancel(row["amount"])
            self._publish(self.db.update_order(row["id"], status="erro", error=str(exc)[:300]))
            return
        self._publish(self.db.update_order(row["id"], status="aberta", broker_order_id=ticket.order_id,
                                           expires_at=ticket.expires_at, account=ticket.account))
        wait = ticket.expires_at - self._now()
        if wait > 0:
            self._sleep(wait + 1)
        give_up = ticket.expires_at + RESULT_TIMEOUT
        while True:
            try:
                res = broker.order_result(ticket)
            except BrokerError as exc:
                log.warning("Resultado da ordem %s: %s", row["id"], exc)
                res = None
            if res is not None:
                with self._lock:
                    self.risk.closed(res.result, res.profit, row["amount"])
                self._publish(self.db.update_order(row["id"], status=res.result, profit=res.profit))
                return
            if self._now() > give_up:
                # Sem resposta da IQ: para a gestão de risco conta como perda (o lado seguro).
                with self._lock:
                    self.risk.closed(LOSS, -row["amount"], row["amount"])
                self._publish(self.db.update_order(row["id"], status="sem_resultado",
                                                   error="A IQ não informou o resultado; confira no histórico da corretora"))
                return
            self._sleep(1)

    def _publish(self, row: dict | None) -> None:
        if row is not None:
            self.hub.publish({"type": "order", "order": row, "risk": self.snapshot()})
