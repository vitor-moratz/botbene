"""Observador: preço ao vivo do par que está na tela quando o bot não cuida dele.

Serve para olhar e operar na mão com o bot parado, ou num par fora da lista do bot. Só alimenta o
gráfico: não roda estratégia, não grava sinal e não manda ordem. Cuida de um par por vez.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from app.broker.base import Broker, BrokerError
from app.ldp.engine import LdpEngine
from app.market.store import CandleStore
from app.service.chart import candle_dict

if TYPE_CHECKING:
    from app.service.bot import BotService

log = logging.getLogger(__name__)

POLL_SECONDS = 0.5
RETRY_SECONDS = 5  # espera depois de uma falha ou sem conexão
CONNECTION_CHECK_SECONDS = 30  # com o bot parado, ninguém mais confere se a conexão continua viva
IDLE_SECONDS = 300  # sem nenhum painel aberto por isso, para sozinho
MAX_POLL_FAILURES = 3  # leituras seguidas com erro antes de carregar tudo de novo
STALL_SECONDS = 150  # par aberto sem preço novo por isso: reabre o stream
STREAM_GRACE_SECONDS = 3
STORE_MAXLEN = 1500


class _Watch:
    """Um par sendo observado. Trocar de par cria outro, e este termina sozinho."""

    def __init__(self, asset: str, timeframe: int) -> None:
        self.asset = asset
        self.timeframe = timeframe
        self.cancel = threading.Event()
        self.thread: threading.Thread | None = None
        self.runner: Any = None
        self.broker: Broker | None = None
        self.streaming = False
        self.state = "carregando"  # carregando | ao_vivo | sem_conexao
        self.error: str | None = None
        self.next_check = 0.0

    @property
    def alive(self) -> bool:
        return self.thread is not None and self.thread.is_alive()


class PairWatcher:
    def __init__(self, bot: BotService, make_runner: Callable[[str, int], Any], poll_seconds: float = POLL_SECONDS,
                 retry_seconds: float = RETRY_SECONDS, idle_seconds: float = IDLE_SECONDS) -> None:
        self._bot = bot
        self._make_runner = make_runner
        self.poll_seconds = poll_seconds
        self.retry_seconds = retry_seconds
        self.idle_seconds = idle_seconds
        self._lock = threading.Lock()
        self._watch: _Watch | None = None

    @property
    def asset(self) -> str | None:
        w = self._watch
        return w.asset if w is not None and w.alive else None

    def runner_for(self, asset: str) -> Any:
        w = self._watch
        return w.runner if w is not None and w.alive and w.asset == asset else None

    def view(self) -> dict | None:
        w = self._watch
        return {"asset": w.asset, "state": w.state, "error": w.error} if w is not None and w.alive else None

    def watch(self, asset: str, timeframe: int) -> None:
        with self._lock:
            old = self._watch
            if old is not None and old.alive and old.asset == asset and old.timeframe == timeframe:
                return
            if old is not None:
                old.cancel.set()
            w = _Watch(asset, timeframe)
            w.thread = threading.Thread(target=self._run, args=(w,), name=f"observa-{asset}", daemon=True)
            self._watch = w
            w.thread.start()

    def stop(self) -> None:
        with self._lock:
            w, self._watch = self._watch, None
        if w is not None:
            w.cancel.set()

    # ------------------------------------------------------------------ thread

    def _run(self, w: _Watch) -> None:
        idle_since: float | None = None
        failures = 0
        try:
            while not w.cancel.is_set():
                mono = time.monotonic()
                idle_since = None if self._bot.hub.clients else (idle_since or mono)
                if idle_since is not None and mono - idle_since >= self.idle_seconds:
                    return
                broker = self._connection(w)
                if broker is None:
                    self._set_state(w, "sem_conexao")
                    w.cancel.wait(self.retry_seconds)
                    continue
                try:
                    if broker is not w.broker or w.runner is None:
                        self._load(w, broker)
                    elif not w.cancel.is_set():
                        self._poll(w, broker)
                    failures = 0
                except BrokerError as exc:
                    failures += 1
                    log.debug("Observador de %s: %s", w.asset, exc)
                    if w.runner is None or failures >= MAX_POLL_FAILURES:
                        failures = 0
                        w.broker, w.runner, w.streaming, w.error = None, None, False, str(exc)
                        self._set_state(w, "sem_conexao")
                        w.cancel.wait(self.retry_seconds)
                        continue
                w.cancel.wait(self.poll_seconds)
        except Exception:  # noqa: BLE001 - problema aqui não pode derrubar o servidor nem o bot
            log.exception("Observador de %s parou com erro", w.asset)
        finally:
            self._release(w)

    def _connection(self, w: _Watch) -> Broker | None:
        """Com o bot ligado, a conexão é dele e o vigia cuida dela. Com o bot parado, usa a compartilhada."""
        bot = self._bot
        if bot.status not in ("parado", "erro"):
            return bot.current_broker()
        mono = time.monotonic()
        if w.broker is not None and w.broker is bot.current_broker() and mono < w.next_check:
            return w.broker
        w.next_check = mono + CONNECTION_CHECK_SECONDS
        try:
            return bot.shared_broker()  # respeita a espera entre logins
        except BrokerError as exc:
            w.error = str(exc)
            return None

    def _load(self, w: _Watch, broker: Broker) -> None:
        bot = self._bot
        w.broker, w.runner, w.streaming = broker, None, False
        self._set_state(w, "carregando")
        history = broker.get_candles(w.asset, w.timeframe, bot.settings.history_candles)
        if w.cancel.is_set():
            return
        if not history:
            raise BrokerError(f"Nenhuma vela recebida para {w.asset}")
        store = CandleStore(w.asset, w.timeframe, maxlen=STORE_MAXLEN)
        store.load_history(history)
        engine = LdpEngine()
        step = None
        for candle in store.closed:
            step = engine.process(candle)
        r = self._make_runner(w.asset, w.timeframe)
        r.store, r.engine, r.last_step = store, engine, step
        r.tradable = broker.tradable(w.asset)
        r.payout = broker.payout_now(w.asset) or bot.settings.default_payout
        bot.db.save_candles(w.asset, w.timeframe, history)
        bot.currency = broker.currency()  # a marca da moeda no painel vale mesmo sem o bot ter rodado
        with bot._lock:
            w.runner = r
        bot.hub.publish({"type": "reload"})  # o histórico já aparece: num par fechado, o stream demora a desistir
        w.streaming = True
        broker.start_stream(w.asset, w.timeframe, 10)
        r.last_data = time.monotonic()
        bot._tick_clock(broker.server_time())
        w.error = None
        self._set_state(w, "ao_vivo")

    def _poll(self, w: _Watch, broker: Broker) -> None:
        bot, r = self._bot, w.runner
        updates = broker.stream_candles(w.asset, w.timeframe)
        mono = time.monotonic()
        if updates:  # o stream devolve sempre as últimas velas: só conta como vivo se algo mudou
            last = updates[-1]
            sig = (last.ts, last.open, last.high, last.low, last.close)
            if sig != r.last_sig:
                r.last_sig, r.last_data = sig, mono
        closed = []
        with bot._lock:
            for candle in updates:
                closed += r.store.ingest(candle)
        now = broker.server_time()
        bot._tick_clock(now)
        if not closed:
            with bot._lock:
                closed += r.store.close_forming_if_expired(now - STREAM_GRACE_SECONDS)
        if closed:
            r.tradable = broker.tradable(w.asset)
            r.payout = broker.payout_now(w.asset) or r.payout
        for candle in closed:
            with bot._lock:
                r.last_step = r.engine.process(candle)
            bot.db.save_candles(w.asset, w.timeframe, [candle])
            bot.hub.publish({"type": "closed", "asset": w.asset, "candle": candle_dict(candle), "status": bot.snapshot()})
        forming = r.store.forming
        if forming is not None and forming != r.last_forming:
            r.last_forming = forming
            bot.hub.publish({"type": "tick", "asset": w.asset, "candle": candle_dict(forming)})
        if r.tradable[0] and mono - r.last_data > STALL_SECONDS:
            log.warning("%s sem preço novo há %d s: reabrindo o stream", w.asset, int(mono - r.last_data))
            r.last_data = mono
            broker.start_stream(w.asset, w.timeframe, 10)

    def _set_state(self, w: _Watch, state: str) -> None:
        if w.state != state and not w.cancel.is_set():
            w.state = state
            self._bot.hub.publish({"type": "status", **self._bot.snapshot()})

    def _release(self, w: _Watch) -> None:
        """Cancela o stream, a não ser que outro observador ou o bot estejam usando o mesmo par."""
        current = self._watch
        if not w.streaming or w.broker is None or self._bot.stream_in_use(w.asset):
            return
        if current is not None and current is not w and current.asset == w.asset:
            return
        try:
            w.broker.release_stream(w.asset, w.timeframe)
        except Exception as exc:  # noqa: BLE001 - conexão ruim: o stream morre junto com ela
            log.debug("%s: stream não cancelado: %s", w.asset, exc)
