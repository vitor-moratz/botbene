"""Ordens na conta demo: passa pela gestão de risco, envia, espera o vencimento e grava o resultado.

Cada ordem roda numa thread própria (enviar leva ~1 s e o resultado só sai no fim do minuto),
para não travar a leitura do mercado.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from app.broker.base import BINARY, KIND_LABELS, Broker, BrokerError, OrderRefused, OrderTicket
from app.db.database import Database
from app.paper import DRAW, LOSS, WIN, order_units
from app.risk import RiskConfig, RiskManager
from app.service.events import EventHub
from app.strategies import MANUAL

log = logging.getLogger(__name__)

RESULT_TIMEOUT = 90  # segundos depois do vencimento sem resultado = "sem_resultado"
MANUAL_REPEAT_SECONDS = 1.0  # mesmo par e direção em menos que isso é clique duplo


class DuplicateOrderError(ValueError):
    pass


class OrderManager:
    def __init__(
        self,
        db: Database,
        hub: EventHub,
        broker_provider: Callable[[], Broker],
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], float] = time.time,
        threaded: bool = True,
        current_broker: Callable[[], Broker | None] | None = None,
    ) -> None:
        self.db, self.hub = db, hub
        self._broker = broker_provider
        # Conexão atual, sem abrir uma nova: se o bot reconectou durante a ordem, o resultado pode chegar por ela.
        self._current = current_broker
        self._sleep, self._now = sleep, now
        self._threaded = threaded
        self._lock = threading.Lock()
        self.risk = RiskManager()
        self._manual_open = 0  # entradas manuais abertas: ficam fora da gestão de risco do bot
        self._manual_last: dict[tuple[str, str], float] = {}

    @property
    def open_count(self) -> int:
        with self._lock:
            return self.risk.open_orders + self._manual_open

    def reset(self, cfg: RiskConfig) -> None:
        with self._lock:
            self.risk = RiskManager(cfg)

    def set_config(self, cfg: RiskConfig) -> None:
        """Muda valor/stops no meio da sessão sem zerar o placar."""
        with self._lock:
            self.risk.cfg = cfg

    def restore(self, rows: list[dict]) -> None:
        """Refaz o placar da sessão a partir das ordens gravadas (o servidor reiniciou no meio dela).
        Sem isso, o stop loss voltaria a contar do zero."""
        with self._lock:
            for o in sorted(rows, key=lambda r: (r["requested_at"], r["id"])):
                if o["strategy"] == MANUAL:
                    continue
                if o["status"] in (WIN, LOSS, DRAW):
                    self.risk.closed(o["status"], o.get("profit") or 0.0, o["amount"], o["strategy"])
                elif o["status"] == "sem_resultado":  # como em _run: para a gestão de risco conta como perda
                    self.risk.closed(LOSS, -o["amount"], o["amount"], o["strategy"])

    def waiting_gale(self, strategy: str) -> bool:
        """Esta entrada usa o gale e a ordem anterior do ciclo DELA ainda não tem resultado?"""
        with self._lock:
            return self.risk.gale_open(strategy)

    def record_blocked(self, *, asset: str, timeframe: int, strategy: str, direction: str, ref_price: float | None,
                       signal_id: int | None, payout: float = 0.85, kind: str = BINARY, account: str | None = None,
                       why: str) -> dict:
        """Entrada que o bot não chegou a mandar (ex.: a janela fechou esperando o resultado do gale): fica no histórico."""
        with self._lock:
            amount = self.risk.next_stake(payout, strategy)
            gale = self.risk.cycle(strategy).level if self.risk.uses_gale(strategy) else 0
        row = self.db.add_order(asset=asset, timeframe=timeframe, strategy=strategy, direction=direction,
                                ref_price=ref_price, signal_id=signal_id, option_type=kind, gale=gale, amount=amount,
                                status="bloqueada", error=why, **({"account": account} if account else {}))
        self._publish(row)
        return row

    def snapshot(self, payout: float = 0.85) -> dict:
        with self._lock:
            return self.risk.snapshot(payout) | {"manual_open": self._manual_open}

    def submit_manual(self, *, asset: str, timeframe: int, direction: str, amount: float, minutes: int,
                      ref_price: float | None, requested_at: int, account: str | None, kind: str = BINARY) -> dict:
        """Entrada feita na mão: a decisão é do usuário, então os stops do bot não bloqueiam nem contam com ela."""
        key = (asset, direction)
        with self._lock:
            mono = time.monotonic()
            if mono - self._manual_last.get(key, -MANUAL_REPEAT_SECONDS) < MANUAL_REPEAT_SECONDS:
                raise DuplicateOrderError("Clique repetido: essa entrada já foi enviada.")
            self._manual_last[key] = mono
            self._manual_open += 1
        row = self.db.add_order(asset=asset, timeframe=timeframe, strategy=MANUAL, direction=direction, ref_price=ref_price,
                                signal_id=None, gale=0, amount=amount, status="enviando", requested_at=requested_at,
                                option_type=kind, **({"account": account} if account else {}))
        self._publish(row)
        self._start(row, minutes)
        return row

    def _start(self, row: dict, minutes: int = 1, fallback: str | None = None) -> None:
        if self._threaded:
            threading.Thread(target=self._run, args=(row, minutes, fallback), name=f"ordem-{row['id']}",
                             daemon=True).start()
        else:
            self._run(row, minutes, fallback)

    def submit(self, *, asset: str, timeframe: int, strategy: str, direction: str, ref_price: float | None,
               signal_id: int | None, payout: float = 0.85, kind: str = BINARY, fallback: str | None = None,
               account: str | None = None) -> dict:
        """`fallback`: o outro tipo de opção, se a IQ recusar `kind` (só quando ela com certeza não comprou).
        `account`: a conta do bot, para a ordem bloqueada ou recusada também ficar registrada nela."""
        base = {"asset": asset, "timeframe": timeframe, "strategy": strategy, "direction": direction,
                "ref_price": ref_price, "signal_id": signal_id, "option_type": kind,
                **({"account": account} if account else {})}
        with self._lock:
            ok, why = self.risk.check(payout, strategy)
            amount = self.risk.next_stake(payout, strategy)
            base["gale"] = self.risk.cycle(strategy).level if self.risk.uses_gale(strategy) else 0
            if ok:
                self.risk.opened(amount, strategy)
        if not ok:
            row = self.db.add_order(**base, amount=amount, status="bloqueada", error=why)
            self._publish(row)
            return row
        row = self.db.add_order(**base, amount=amount, status="enviando")
        self._publish(row)
        self._start(row, fallback=fallback)
        return row

    def _not_sent(self, row: dict) -> None:
        with self._lock:
            if row["strategy"] == MANUAL:
                self._manual_open = max(0, self._manual_open - 1)
            else:
                self.risk.cancel(row["amount"], row["strategy"])

    def _closed(self, row: dict, result: str, profit: float) -> None:
        with self._lock:
            if row["strategy"] == MANUAL:
                self._manual_open = max(0, self._manual_open - 1)
            else:
                self.risk.closed(result, profit, row["amount"], row["strategy"])

    def _buy(self, broker: Broker, row: dict, minutes: int, fallback: str | None) -> OrderTicket:
        """Compra no tipo da ordem. Se a IQ recusar com certeza (nada comprado) e houver outro tipo, tenta ele."""
        kind = row.get("option_type") or BINARY
        try:
            return broker.buy(row["asset"], row["direction"], row["amount"], minutes, kind=kind)
        except OrderRefused as exc:
            if not fallback or fallback == kind:
                raise
            other = KIND_LABELS.get(fallback, fallback)
            log.warning("Ordem %s: %s. Tentando na %s", row["id"], exc, other)
            try:
                return broker.buy(row["asset"], row["direction"], row["amount"], minutes, kind=fallback)
            except Exception as exc2:  # noqa: BLE001 - a mensagem diz o que aconteceu nos dois tipos
                raise BrokerError(f"{exc}; na {other}: {exc2}") from exc2

    def _run(self, row: dict, minutes: int = 1, fallback: str | None = None) -> None:
        try:
            broker = self._broker()
            ticket = self._buy(broker, row, minutes, fallback)
        except Exception as exc:  # noqa: BLE001 - qualquer falha vira "erro" na ordem
            log.warning("Ordem %s não enviada: %s", row["id"], exc)
            self._not_sent(row)
            self._publish(self.db.update_order(row["id"], status="erro", error=str(exc)[:300]))
            return
        self._publish(self.db.update_order(row["id"], status="aberta", broker_order_id=ticket.order_id,
                                           expires_at=ticket.expires_at, account=ticket.account,
                                           option_type=ticket.kind))
        wait = ticket.expires_at - self._now()
        if wait > 0:
            self._sleep(wait + 1)
        give_up = ticket.expires_at + RESULT_TIMEOUT
        while True:
            res = self._result(row["id"], ticket, broker)
            if res is not None:
                self._closed(row, res.result, res.profit)
                self._publish(self.db.update_order(row["id"], status=res.result, profit=res.profit))
                self._to_signal(row, res.result, res.profit)
                return
            if self._now() > give_up:
                # Sem resposta da IQ: para a gestão de risco conta como perda (o lado seguro).
                self._closed(row, LOSS, -row["amount"])
                self._publish(self.db.update_order(row["id"], status="sem_resultado",
                                                   error="A IQ não informou o resultado; confira no histórico da corretora"))
                return
            self._sleep(1)

    def _to_signal(self, row: dict, result: str, profit: float) -> None:
        """O resultado da corretora vale para o sinal que gerou a ordem: é ele que entra no acerto da estratégia."""
        if row.get("signal_id") is None:
            return
        try:
            signal = self.db.apply_order_result(row["signal_id"], row["id"], result, order_units(result, profit, row["amount"]))
        except Exception as exc:  # noqa: BLE001 - o resultado da ordem já está gravado; o servidor acerta ao reabrir
            log.warning("Ordem %s: não deu para passar o resultado ao sinal %s: %s", row["id"], row["signal_id"], exc)
            return
        if signal is not None:
            self.hub.publish({"type": "result", "signal": signal})

    def _result(self, order_id: int, ticket, broker: Broker):
        """Procura o resultado na conexão que enviou a ordem e, se o bot reconectou, também na atual.
        Qualquer falha aqui só adia: depois de RESULT_TIMEOUT a ordem fica "sem_resultado"."""
        brokers = [broker]
        current = self._current() if self._current is not None else None
        if current is not None and current is not broker:
            brokers.append(current)
        for b in brokers:
            try:
                res = b.order_result(ticket)
            except Exception as exc:  # noqa: BLE001 - conexão fechada no meio, erro da biblioteca etc.
                log.debug("Resultado da ordem %s: %s", order_id, exc)
                continue
            if res is not None:
                return res
        return None

    def _publish(self, row: dict | None) -> None:
        if row is not None:
            self.hub.publish({"type": "order", "order": row, "risk": self.snapshot()})
