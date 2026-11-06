"""O bot: lê o mercado ao vivo de um ou mais pares, registra as entradas de cada estratégia ligada
(modo paper) e manda ordem pelas que estão em "Operar", conforme o modo.

Estratégia não é script. Scripts (LDP v1.3, WIKI PRO) só desenham no gráfico (service/chart.py).
As estratégias entram DENTRO da vela: no fechamento da vela k "armam" um setup; a entrada só acontece
se o gatilho disparar nos primeiros 15 s da vela k+1, com vencimento no fim dela.
O caminho de sinal no fechamento (`strategies_factory`, entrada na abertura da vela seguinte) fica
disponível, mas nada roda nele em produção.

Modo de aprovação (só para as estratégias em "Operar"): cada setup armado vira
um pedido no painel, com o trecho do gráfico. Aprovado antes do gatilho = a ordem sai no toque;
aprovado depois do toque (ainda dentro dos 15 s) = a ordem sai no preço do momento.

Ao iniciar, roda tudo no histórico carregado (backtest imediato, origem "backtest"); para as de
dentro da vela usa velas de 5 s, para saber se o gatilho disparou mesmo dentro dos 15 s.

Vigia da conexão: a biblioteca da IQ às vezes trava ou perde o websocket sem avisar. O bot reconecta
sozinho quando a IQ para de responder algumas vezes seguidas, quando o horário da IQ para de andar,
quando a biblioteca diz que caiu, ou quando nenhum par aberto recebe preço novo por um tempo. Na
reconexão, fecha a conexão velha, abre outra, recarrega o histórico (cobre o buraco) e volta a rodar.
"""

from __future__ import annotations

import itertools
import logging
import math
import threading
import time
from collections import deque
from collections.abc import Callable, Iterable

from app.analytics.stats import breakeven
from app.broker.base import Broker, BrokerError
from app.config import Settings
from app.db.database import Database
from app.ldp.engine import EngineStep, LdpEngine
from app.market.candle import Candle, is_otc
from app.market.store import CandleStore
from app.paper import CANCELED, judge, profit_units
from app.service.chart import build_chart, build_reading, candle_dict, ldp_overlay, reading
from app.service.config_store import ORDER_MODES, ConfigStore, UserConfig
from app.service.events import EventHub
from app.service.orders import OrderManager
from app.strategies import STRATEGY_ORDER
from app.strategies.base import Signal, Strategy
from app.strategies.intra import default_intra, plan_all
from app.strategies.ldp_apostila import ArmedSetup, Plan, gap_ok, touched
from app.strategies.ldp_apostila import backtest as intra_backtest

log = logging.getLogger(__name__)

POLL_SECONDS = 0.5
STREAM_GRACE_SECONDS = 3
STORE_MAXLEN = 1500
SUB_TIMEFRAME = 5  # velas curtas usadas no backtest do gatilho de 15 s
MAX_SUB_CANDLES = 6000
EXCERPT_CANDLES = 60  # velas no gráfico de cada pedido de aprovação
READING_CONTEXT = 300  # velas antes do trecho mostrado, para a leitura já chegar nele com lotes e regiões
APPROVALS_KEPT = 12
OPEN_APPROVAL = ("aguardando", "aprovado", "disparou")

# Vigia da conexão
MAX_POLL_FAILURES = 3  # leituras seguidas com erro antes de reconectar (uma falha solta é normal)
CLOCK_STALL_SECONDS = 60  # horário da IQ parado por isso = websocket morto
STALL_SECONDS = 150  # par aberto sem nenhum preço novo por isso = stream morto
CONNECTION_CHECK_SECONDS = 30
RECONNECT_WAITS = (5, 10, 20, 30, 60, 120, 300)  # espera entre tentativas; depois fica na última
CONNECT_BACKOFF_SECONDS = 30  # depois de um login que falhou, o painel e o arquivo de velas não tentam outro antes disso
# Erros que não melhoram tentando de novo (senha errada, sem login, REAL travada): viram "erro" na hora.
PERMANENT_ERRORS = ("invalid_credentials", "Preencha IQ_EMAIL", "2FA", "Conta REAL bloqueada", "iqoptionapi não instalada")


def _permanent(exc: Exception) -> bool:
    return any(key in str(exc) for key in PERMANENT_ERRORS)


class BotBusyError(RuntimeError):
    pass


class AssetRunner:
    """Tudo o que o bot acompanha de um par."""

    def __init__(self, asset: str, timeframe: int, strategies: list[Strategy]) -> None:
        self.asset = asset
        self.timeframe = timeframe
        self.strategies = strategies
        self.store: CandleStore | None = None
        self.engine: LdpEngine | None = None
        self.intra: list | None = None
        self.last_step: EngineStep | None = None
        self.armed: list[ArmedSetup] = []
        self.plan_reasons: list[str] = []
        self.payout: float | None = None
        self.session_id: int | None = None
        self.error: str | None = None
        self.tradable: tuple[bool, str] = (True, "ok")  # binária de 1 min aberta neste par? (conferido a cada vela)
        self.gap_checked: set[tuple] = set()
        self.last_forming: Candle | None = None
        # Vigia: último dado diferente que o stream entregou e quando (relógio monotônico).
        self.last_sig: tuple | None = None
        self.last_data = time.monotonic()
        self.stream_restarted = False

    @property
    def ready(self) -> bool:
        return self.store is not None and self.engine is not None

    def clear(self) -> None:
        """Esquece o estado do mercado (antes de recarregar tudo numa reconexão)."""
        self.store = self.engine = self.intra = None
        self.last_step = None
        self.armed, self.plan_reasons = [], []
        self.gap_checked = set()
        self.last_forming = self.last_sig = None
        self.stream_restarted = False

    def summary(self) -> dict:
        last = self.store.closed[-1] if self.store and self.store.closed else None
        forming = self.store.forming if self.store else None
        price = forming.close if forming else (last.close if last else None)
        return {"asset": self.asset, "payout": self.payout, "price": price, "armed": len(self.armed), "error": self.error,
                "tradable": self.tradable[0], "tradable_note": None if self.tradable[0] else self.tradable[1]}


class BotService:
    def __init__(
        self,
        settings: Settings,
        db: Database,
        hub: EventHub,
        broker_factory: Callable[[], Broker],
        strategies_factory: Callable[[], list[Strategy]] = list,
        config: ConfigStore | None = None,
        orders: OrderManager | None = None,
    ) -> None:
        self.settings = settings
        self.db = db
        self.hub = hub
        self._broker_factory = broker_factory
        self._broker: Broker | None = None
        self._broker_lock = threading.Lock()
        self._connect_error: str | None = None  # motivo da última tentativa de entrar que falhou
        self._connect_retry_at = 0.0
        self._strategies_factory = strategies_factory
        self.config = config or ConfigStore(settings.resolved_data_dir() / "config.json", settings.iq_email, settings.iq_password)
        # Espera do vencimento pelo horário da IQ (o relógio do WSL pode estar adiantado).
        self.orders = orders or OrderManager(db, hub, self.shared_broker, now=lambda: self._now(),
                                             current_broker=lambda: self._broker)
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

        self.status = "parado"
        self.error: str | None = None
        self.progress: str | None = None
        self.timeframe = 60
        self.account: str | None = None
        self.currency = "USD"
        self.started_at: int | None = None
        self.runners: dict[str, AssetRunner] = {}
        self.focus: str | None = None
        self.armed_log: deque[dict] = deque(maxlen=20)
        self.approvals: list[dict] = []
        self._approval_seq = itertools.count(1)
        self._clock: tuple[float, float] | None = None  # (horário do servidor, monotonic) da última leitura
        # Vigia da conexão (os limites ficam no objeto para os testes poderem encurtar).
        self.poll_seconds = POLL_SECONDS
        self.max_poll_failures = MAX_POLL_FAILURES
        self.clock_stall_seconds = CLOCK_STALL_SECONDS
        self.stall_seconds = STALL_SECONDS
        self.connection_check_seconds = CONNECTION_CHECK_SECONDS
        self.reconnect_waits = RECONNECT_WAITS
        self._poll_failures = 0
        self._clock_seen: tuple[float, float] | None = None  # (horário da IQ, monotonic) da última mudança
        self._next_conn_check = 0.0
        self.connection = self._fresh_connection()
        self.hung_attempts = 0  # tentativas seguidas de reconectar em que a IQ nem respondeu (lido pelo guarda do processo)
        cfg = self.config.get()
        self.mode, self.order_strategies = cfg.mode, set(cfg.operating)
        self.filters = cfg
        self.running_strategies = set(cfg.running)  # ligar ou desligar uma estratégia vale no próximo início

    # ------------------------------------------------------------------ controle

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def runner(self, asset: str | None = None) -> AssetRunner | None:
        return self.runners.get(asset or self.focus or "")

    def configure(self, assets: Iterable[str], timeframe: int) -> None:
        assets = list(dict.fromkeys(assets))
        if not assets:
            raise ValueError("Escolha pelo menos um ativo")
        self.timeframe = timeframe
        cfg = self.config.get()
        self.order_strategies = set(cfg.operating)
        self.running_strategies = set(cfg.running)
        self.runners = {a: AssetRunner(a, timeframe, self._strategies_factory()) for a in assets}
        if self.focus not in self.runners:
            self.focus = assets[0]

    def _intra_for(self, timeframe: int) -> list:
        """As estratégias ligadas (Observar ou Operar). Com todas desligadas, nenhuma roda."""
        return [s for s in default_intra(timeframe) if s.name in self.running_strategies]

    def active_strategies(self) -> list[str]:
        names = [s.name for s in self._intra_for(self.timeframe)] + [s.name for s in self._strategies_factory()]
        return [n for n in STRATEGY_ORDER if n in names]

    def start(self, assets: Iterable[str] | None = None, timeframe: int | None = None) -> None:
        with self._lock:
            if self.running:
                raise BotBusyError("O bot já está rodando. Pare antes de trocar os ativos.")
            cfg = self.config.get()
            if cfg.account == "REAL" and not cfg.stop_loss:
                raise ValueError("Na conta real, defina um stop loss (Configuração → Gestão de risco) antes de iniciar.")
            self._stop.clear()
            self.error = None
            self.configure(list(assets) if assets else cfg.assets, timeframe or cfg.timeframe)
            self._apply(cfg)
            self.orders.reset(cfg.risk())
            self.approvals = []
            self.armed_log.clear()
            self.started_at = int(time.time())
            self.connection = self._fresh_connection()
            self.hung_attempts = 0
            self._set_status("conectando")
            self._thread = threading.Thread(target=self._run, name="botbene", daemon=True)
            self._thread.start()

    def stop(self, wait: float = 15.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(wait)

    def resume_info(self, why: str) -> dict:
        """O que o servidor precisa saber para retomar esta sessão depois de reiniciar sozinho."""
        with self._lock:
            return {"at": time.time(), "why": why, "resume": self.running, "assets": list(self.runners),
                    "timeframe": self.timeframe, "started_at": self.started_at, "drops": self.connection["drops"]}

    def resume(self, info: dict) -> None:
        """Volta a rodar depois que o servidor reiniciou sozinho, com o placar da sessão (stops e gale) refeito.
        Só na demo: na conta real o bot não volta a mandar ordem sem alguém olhar."""
        why = info.get("why") or "travou"
        if self.config.get().account != "PRACTICE":
            with self._lock:
                self.error = (f"O servidor reiniciou sozinho ({why}). Na conta real o bot não volta sozinho: "
                              "confira a tela e clique em Iniciar bot.")
            self._set_status("erro")
            return
        started_at = info.get("started_at")
        self.start(info.get("assets") or None, info.get("timeframe"))
        with self._lock:
            self.started_at = started_at or self.started_at
            self.connection["drops"] = int(info.get("drops") or 0) + 1
            self.connection["last_drop"] = {"at": info.get("at") or time.time(), "back_at": time.time(),
                                            "reason": f"servidor reiniciado: {why}", "attempts": 1}
        if started_at:
            self.orders.restore(self.db.list_orders(limit=5000, since_ts=started_at))

    def reset_history(self) -> dict:
        """Zera o histórico (com cópia de segurança). Só com o bot parado."""
        with self._lock:
            if self.running:
                raise BotBusyError("Pare o bot antes de zerar o histórico.")
            out = self.db.reset_history(self.settings.resolved_data_dir() / "backups")
            self.runners, self.focus = {}, None
            self.approvals, self.started_at, self.error = [], None, None
            self.armed_log.clear()
            self.orders.reset(self.config.get().risk())
        self.hub.publish({"type": "status", **self.snapshot()})
        self.hub.publish({"type": "reload"})
        return out

    def set_focus(self, asset: str) -> None:
        with self._lock:
            if asset not in self.runners:
                raise KeyError(asset)
            self.focus = asset
        self.hub.publish({"type": "status", **self.snapshot()})

    def apply_config(self, cfg: UserConfig) -> None:
        """Modo, quem opera e gestão de risco valem na hora; ligar ou desligar estratégia, ativos e vela, no próximo início."""
        with self._lock:
            self._apply(cfg)
            self.orders.set_config(cfg.risk())
            if self.mode not in ORDER_MODES:
                for ap in self.approvals:
                    if ap["status"] in OPEN_APPROVAL:
                        self._close_approval(ap, "cancelado: modo só sinais")
        self.hub.publish({"type": "status", **self.snapshot()})

    def _apply(self, cfg: UserConfig) -> None:
        self.mode, self.order_strategies = cfg.mode, set(cfg.operating)
        self.filters = cfg  # payout mínimo e horário de operação (UserConfig.entry_block)

    def shared_broker(self, force: bool = False) -> Broker:
        """Conexão com a corretora compartilhada entre o bot, o resolvedor e as ordens.

        Se a última tentativa de entrar falhou há pouco, quem só quer ler algo (saldo no painel, arquivo de
        velas) recebe o mesmo erro na hora, sem abrir outro login. `force`: o bot e o botão "Testar conexão"."""
        with self._broker_lock:
            if self._broker is not None:
                try:
                    if self._broker.is_connected():
                        return self._broker
                except BrokerError:
                    pass
                old, self._broker = self._broker, None
                self._close_quietly(old)  # fecha antes de abrir outra (a biblioteca guarda estado global)
            if not force and self._connect_error and time.monotonic() < self._connect_retry_at:
                raise BrokerError(self._connect_error)
            try:
                self._broker = self._broker_factory()
            except BrokerError as exc:
                # Senha recusada ou 2FA: só tenta de novo quando alguém agir (Testar conexão, Iniciar bot, trocar o
                # login). Repetir sozinho pode bloquear a conta e, no 2FA, cada tentativa manda um SMS.
                wait = math.inf if _permanent(exc) else CONNECT_BACKOFF_SECONDS
                self._connect_error, self._connect_retry_at = str(exc), time.monotonic() + wait
                raise
            self._connect_error = None
            return self._broker

    @staticmethod
    def _close_quietly(broker: Broker) -> None:
        try:
            broker.disconnect()
        except Exception as exc:  # noqa: BLE001 - conexão que já morreu pode não fechar direito
            log.debug("Conexão velha não fechou: %s", exc)

    def test_connection(self) -> dict:
        """Entra na IQ com o login salvo e lê o saldo. Com o bot parado, refaz a conexão do zero."""
        if not self.running:
            self._drop_broker()
        broker = self.shared_broker(force=True)
        account = getattr(broker, "account", None)
        return {"account": getattr(account, "value", account), "balance": broker.balance(), "currency": broker.currency()}

    def account_info(self) -> dict:
        """Conta escolhida, a conta em que a conexão está e o saldo dela."""
        chosen = self.config.get().account
        if self.status == "reconectando":  # o vigia cuida da conexão: o painel não abre outra em paralelo
            return {"chosen": chosen, "account": None, "balance": None, "currency": None, "error": "reconectando à IQ Option"}
        try:
            broker = self.shared_broker()
            account = getattr(broker, "account", None)
            return {"chosen": chosen, "account": getattr(account, "value", account), "balance": broker.balance(),
                    "currency": broker.currency(), "error": None}
        except Exception as exc:  # noqa: BLE001 - sem conexão: o painel mostra o motivo
            return {"chosen": chosen, "account": None, "balance": None, "currency": None, "error": str(exc)}

    def switch_account(self, account: str, confirm: str | None = None) -> dict:
        """Troca entre demo e real. Só com o bot parado; a real pede a palavra REAL digitada."""
        if account not in ("PRACTICE", "REAL"):
            raise ValueError("Conta inválida")
        if self.running:
            raise BotBusyError("Pare o bot antes de trocar de conta.")
        if account == "REAL" and (confirm or "").strip().upper() != "REAL":
            raise ValueError("Para usar a conta real, digite REAL para confirmar.")
        self.config.update({"account": account})
        self._drop_broker()  # a próxima conexão já entra na conta escolhida
        info = self.account_info()
        self.hub.publish({"type": "status", **self.snapshot()})
        return info

    def invalidate_broker(self) -> None:
        with self._broker_lock:
            self._connect_error = None  # login novo: vale tentar de novo
        if not self.running:  # com o bot rodando, a troca de login vale no próximo início
            self._drop_broker()

    def _drop_broker(self) -> None:
        with self._broker_lock:
            old, self._broker = self._broker, None
            self._connect_error = None
        if old is not None:
            old.disconnect()

    # ------------------------------------------------------------------ leitura (painel)

    def snapshot(self) -> dict:
        with self._lock:
            r = self.runner()
            last = r.store.closed[-1] if r and r.store and r.store.closed else None
            forming = r.store.forming if r and r.store else None
            armed = [a.to_dict() | {"asset": run.asset} for run in self.runners.values() for a in run.armed]
            payout = r.payout if r else None
            return {
                "status": self.status,
                "error": self.error,
                "progress": self.progress,
                "asset": r.asset if r else None,
                "assets": [run.summary() for run in self.runners.values()],
                "timeframe": self.timeframe,
                "account": self.account,
                "chosen_account": self.config.get().account,
                "currency": self.currency,
                "server_time": self._now(),
                "payout": payout,
                "breakeven": breakeven(payout) if payout else None,
                "session_id": r.session_id if r else None,
                "started_at": self.started_at,
                "last_candle": candle_dict(last) if last else None,
                "forming": candle_dict(forming) if forming else None,
                "reading": reading(r.engine, r.last_step) if r else None,
                "armed": armed,
                "plan_reasons": list(r.plan_reasons) if r else [],
                "armed_log": list(self.armed_log),
                "approvals": [self._approval_view(ap) for ap in self.approvals],
                "mode": self.mode,
                "order_strategies": sorted(self.order_strategies),
                "active_strategies": self.active_strategies(),
                "risk": self.orders.snapshot(payout or self.settings.default_payout),
                "connection": dict(self.connection),
            }

    def chart(self, limit: int = 300, asset: str | None = None) -> dict:
        with self._lock:
            r = self.runner(asset)
            if r is not None and r.ready:
                candles = r.store.closed
                asset, tf, engine, step, forming = r.asset, r.timeframe, r.engine, r.last_step, r.store.forming
            else:
                candles, asset, tf, engine, step, forming = [], asset or self.focus, self.timeframe, None, None, None
        if not candles:
            # Bot parado: mostra a última sessão a partir do banco.
            if asset is None:
                last = self.db.last_session()
                if last is None:
                    return build_chart("", tf, [], limit, [], None, None)
                asset, tf = last.asset, last.timeframe
            candles = self.db.load_candles(asset, tf, max(limit, 300) + 200)
            engine = LdpEngine()
            steps = engine.run(candles)
            step = steps[-1] if steps else None
        since = candles[-limit].ts if len(candles) >= limit else (candles[0].ts if candles else 0)
        signals = self.db.list_signals(asset=asset, since_ts=since - tf, limit=5000)
        orders = self.db.list_orders(asset=asset, since_ts=since - tf, limit=500)
        return build_chart(asset, tf, candles, limit, signals, engine, step, forming, orders=orders,
                           show_wiki=self.config.get().chart_scripts.get("wiki_pro", False))

    def reading_view(self, limit: int = 240, asset: str | None = None) -> dict:
        """A leitura do estudo no gráfico. Roda à parte: nenhuma estratégia usa isto ainda."""
        with self._lock:
            r = self.runner(asset)
            if r is not None and r.ready:
                candles, asset, tf = list(r.store.closed), r.asset, r.timeframe
            else:
                candles, asset, tf = [], asset or self.focus, self.timeframe
        if not candles:
            if asset is None:
                last = self.db.last_session()
                if last is None:
                    return build_reading("", tf, [], limit)
                asset, tf = last.asset, last.timeframe
            candles = self.db.load_candles(asset, tf, limit + READING_CONTEXT)
        return build_reading(asset, tf, candles[-(limit + READING_CONTEXT):], limit)

    # ------------------------------------------------------------------ thread do bot

    def _run(self) -> None:
        reason = "parado pelo usuário"
        broker: Broker | None = None
        try:
            try:
                broker = self.shared_broker(force=True)
                self._bootstrap(broker)
                self._mark_healthy()
                self._set_status("rodando")
            except BrokerError as exc:
                if _permanent(exc):
                    raise
                # A IQ não respondeu ao entrar (acontece): tenta de novo sozinho, como numa queda.
                broker = self._recover(self._broker, f"não conseguiu conectar ({exc})", initial=True)
            while broker is not None and not self._stop.is_set():
                problem = self._poll_guarded(broker)
                if problem:
                    broker = self._recover(broker, problem)  # None = parado no meio da reconexão
                    continue
                self._stop.wait(self.poll_seconds)
        except Exception as exc:  # noqa: BLE001 - qualquer falha vira status de erro no painel
            log.exception("Bot parou com erro")
            reason = f"erro: {exc}"
            with self._lock:
                self.error = str(exc)
            self._set_status("erro")
        finally:
            for r in self.runners.values():
                if broker is not None and r.ready:
                    try:
                        broker.stop_stream(r.asset, r.timeframe)
                    except Exception:  # noqa: BLE001 - a IQ às vezes não confirma; não importa ao parar
                        pass
                if r.session_id is not None:
                    self.db.end_session(r.session_id, reason)
            with self._lock:
                for r in self.runners.values():
                    r.armed = []
                for ap in self.approvals:
                    if ap["status"] in OPEN_APPROVAL:
                        self._close_approval(ap, "cancelado: bot parado")
                self.progress = None
            if self.status != "erro":
                self._set_status("parado")

    # ------------------------------------------------------------------ vigia da conexão

    @staticmethod
    def _fresh_connection() -> dict:
        return {"state": "ok", "drops": 0, "reason": None, "since": None, "attempt": 0,
                "last_error": None, "last_drop": None, "initial": False}

    def _mark_healthy(self) -> None:
        """Ponto de partida do vigia (logo depois de carregar os pares)."""
        mono = time.monotonic()
        for r in self.runners.values():
            r.last_data, r.stream_restarted = mono, False
        self._poll_failures = 0
        self._clock_seen = None
        self._next_conn_check = mono + self.connection_check_seconds

    def _poll_guarded(self, broker: Broker) -> str | None:
        """Uma volta do bot. Devolve o motivo para reconectar, ou None se está tudo bem."""
        try:
            self._poll(broker)
            problem = self._health(broker)
        except BrokerError as exc:
            self._poll_failures += 1
            log.warning("Falha ao ler a IQ (%d de %d): %s", self._poll_failures, self.max_poll_failures, exc)
            if self._poll_failures >= self.max_poll_failures:
                return f"a IQ parou de responder ({exc})"
            return None
        self._poll_failures = 0
        return problem

    def _health(self, broker: Broker) -> str | None:
        mono = time.monotonic()
        # 1) O horário da IQ chega pelo websocket o tempo todo: parado = conexão morta.
        if self._clock is not None:
            server = self._clock[0]
            if self._clock_seen is None or server != self._clock_seen[0]:
                self._clock_seen = (server, mono)
            elif mono - self._clock_seen[1] > self.clock_stall_seconds:
                return f"o horário da IQ parou de andar há {int(mono - self._clock_seen[1])} s"
        # 2) A biblioteca sabe quando o websocket fechou.
        if mono >= self._next_conn_check:
            self._next_conn_check = mono + self.connection_check_seconds
            if not broker.is_connected():
                return "a biblioteca da IQ avisou que a conexão caiu"
        # 3) Par aberto sem preço novo. Fechado (fim de semana, fora do horário) não conta.
        watched = [r for r in self.runners.values() if r.ready and r.tradable[0]]
        stalled = [r for r in watched if mono - r.last_data > self.stall_seconds]
        if not stalled:
            return None
        if len(stalled) == len(watched) or any(r.stream_restarted for r in stalled):
            quiet = int(min(mono - r.last_data for r in stalled))
            return f"nenhum preço novo da IQ há {quiet} s"
        for r in stalled:  # só alguns pares parados: primeiro tenta reabrir o stream deles
            log.warning("%s sem preço novo há %d s: reabrindo o stream", r.asset, int(mono - r.last_data))
            try:
                broker.stop_stream(r.asset, r.timeframe)
            except BrokerError:
                pass  # a IQ às vezes não confirma
            broker.start_stream(r.asset, r.timeframe, 10)
            r.stream_restarted, r.last_data = True, mono
        return None

    def _recover(self, old: Broker | None, problem: str, initial: bool = False) -> Broker | None:
        """Fecha a conexão com problema, abre outra e recarrega os pares. Tenta até dar certo ou o bot parar.
        `initial`: a primeira conexão nem chegou a funcionar (não conta como queda)."""
        dropped_at = time.time()
        log.warning("Conexão com a IQ com problema (%s): reconectando", problem)
        with self._lock:
            self.connection.update(state="reconectando", reason=problem, since=dropped_at, attempt=0, last_error=None,
                                   initial=initial)
            if not initial:
                self.connection["drops"] += 1
            for ap in self.approvals:
                if ap["status"] in OPEN_APPROVAL:
                    self._close_approval(ap, "cancelado: conexão caiu")
            for r in self.runners.values():
                r.armed = []
        for r in self.runners.values():
            if r.session_id is not None:
                self.db.end_session(r.session_id, f"conexão caiu: {problem}")
                r.session_id = None
        self._set_status("reconectando")
        attempt = 0
        while not self._stop.is_set():
            attempt += 1
            # A biblioteca guarda "conectado" num lugar só para todas as conexões: a velha precisa
            # fechar ANTES de abrir a nova, senão o fechamento dela derruba o aviso da nova.
            self._discard_brokers(old)
            with self._lock:
                self.connection["attempt"] = attempt
                self.progress = f"reconectando à IQ (tentativa {attempt})"
                for r in self.runners.values():
                    r.clear()
            self.hub.publish({"type": "status", **self.snapshot()})
            try:
                broker = self.shared_broker(force=True)
                self._bootstrap(broker)
            except BrokerError as exc:
                if _permanent(exc):  # ex.: a senha mudou: tentar de novo não adianta
                    raise
                log.warning("Reconexão %d falhou: %s", attempt, exc)
                self.hung_attempts = self.hung_attempts + 1 if "não respondeu" in str(exc) else 0
                with self._lock:
                    self.connection["last_error"] = str(exc)
                    self.progress = f"tentativa {attempt} falhou; tentando de novo"
                self.hub.publish({"type": "status", **self.snapshot()})
                old = self._broker
                wait = self.reconnect_waits[min(attempt, len(self.reconnect_waits)) - 1]
                if self._stop.wait(wait):
                    break
                continue
            if self._stop.is_set():  # pediram para parar enquanto reconectava: o _run encerra
                return broker
            back = time.time()
            self.hung_attempts = 0
            log.info("Reconectado à IQ na tentativa %d (%.0f s fora)", attempt, back - dropped_at)
            with self._lock:
                self.connection.update(state="ok", attempt=0, last_error=None, initial=False)
                if not initial:
                    self.connection["last_drop"] = {"at": dropped_at, "back_at": back, "reason": problem, "attempts": attempt}
                self.progress = None
            self._mark_healthy()
            self._set_status("rodando")
            return broker
        return None

    def _discard_brokers(self, old: Broker | None) -> None:
        with self._broker_lock:
            current, self._broker = self._broker, None
        for b in {id(x): x for x in (old, current) if x is not None}.values():
            try:
                b.disconnect()
            except Exception as exc:  # noqa: BLE001 - conexão que já morreu pode não fechar direito
                log.debug("Conexão velha não fechou: %s", exc)

    def _bootstrap(self, broker: Broker) -> None:
        payouts = self._fetch_payouts(broker)
        self.currency = broker.currency()
        runners = list(self.runners.values())
        errors = []
        for i, r in enumerate(runners, 1):
            with self._lock:
                self.progress = f"carregando {r.asset} ({i} de {len(runners)})" if len(runners) > 1 else None
            self.hub.publish({"type": "status", **self.snapshot()})
            try:
                self._bootstrap_runner(broker, r, payouts.get(r.asset))
            except BrokerError as exc:
                log.warning("%s fora do bot: %s", r.asset, exc)
                r.error = str(exc)
                errors.append(str(exc))
        with self._lock:
            self.progress = None
            if not any(r.ready for r in runners):
                raise BrokerError("; ".join(errors) or "Nenhum ativo carregado")
            if self.focus not in self.runners or not self.runners[self.focus].ready:
                self.focus = next(r.asset for r in runners if r.ready)
        self.hub.publish({"type": "reload"})

    def _bootstrap_runner(self, broker: Broker, r: AssetRunner, payout: float | None) -> None:
        tf = r.timeframe
        history = broker.get_candles(r.asset, tf, self.settings.history_candles)
        if not history:
            raise BrokerError(f"Nenhuma vela recebida para {r.asset}. O ativo está aberto agora?")
        store = CandleStore(r.asset, tf, maxlen=STORE_MAXLEN)
        store.load_history(history)
        engine = LdpEngine()
        intra = self._intra_for(tf)
        plans: list[Plan] = []
        step = None
        for c in store.closed:
            step = engine.process(c)
            plans.append(plan_all(intra, step, engine))
        with self._lock:
            r.store, r.engine, r.intra, r.last_step = store, engine, intra, step
            r.payout = payout or self.settings.default_payout
            r.armed = list(plans[-1].armed) if plans else []
            r.plan_reasons = list(plans[-1].reasons) if plans else []
            r.error = None
            account = getattr(broker, "account", None)
            self.account = getattr(account, "value", account)
        self.db.save_candles(r.asset, tf, history)
        r.tradable = broker.tradable(r.asset)
        r.session_id = self.db.start_session(r.asset, tf, self.account or "PRACTICE", r.payout)
        self._resolve_from_history(r, store.closed)
        subs = self._fetch_subcandles(broker, r.asset, tf, len(history))
        self._backtest(r, store.closed, plans, subs)
        broker.start_stream(r.asset, tf, 10)
        self._tick_clock(broker.server_time())
        with self._lock:
            opened = self._open_approvals(r, r.armed, self._now())
        if opened:
            self.hub.publish({"type": "approval", "status": self.snapshot()})

    def _fetch_payouts(self, broker: Broker) -> dict[str, float]:
        try:
            return {k: float(v) for k, v in broker.payouts("turbo").items() if v}
        except Exception as exc:  # noqa: BLE001
            log.warning("Não foi possível ler os payouts: %s", exc)
            return {}

    def _fetch_subcandles(self, broker: Broker, asset: str, tf: int, n_candles: int) -> list[Candle]:
        count = min(MAX_SUB_CANDLES, n_candles * tf // SUB_TIMEFRAME)
        try:
            return broker.get_candles(asset, SUB_TIMEFRAME, count)
        except Exception as exc:  # noqa: BLE001 - sem velas curtas, as de dentro da vela só não entram no backtest
            log.warning("Sem velas de %ds para o backtest de %s: %s", SUB_TIMEFRAME, asset, exc)
            return []

    def _backtest(self, r: AssetRunner, candles: list[Candle], plans: list[Plan], subs: list[Candle]) -> None:
        """Sinais no histórico, avaliados com a vela seguinte (origem "backtest")."""
        tf = r.timeframe
        for strat in r.strategies:
            for sig in strat.scan(candles):
                if sig is None:
                    continue
                k = sig.index
                nxt = candles[k + 1] if k + 1 < len(candles) else None
                if nxt is not None and nxt.ts == candles[k].ts + tf:
                    result = judge(sig.direction.value, nxt.open, nxt.close)
                    extra = {"entry_price": nxt.open, "exit_price": nxt.close, "result": result,
                             "profit": profit_units(result, r.payout or 0.0)}
                elif nxt is None:
                    extra = {}  # sinal da última vela: resolve ao vivo
                else:
                    extra = {"result": CANCELED, "profit": 0.0}  # buraco no histórico
                self._store_signal(r, sig, origin="backtest", **extra)
        for e in intra_backtest(candles, plans, subs, tf):
            self._store_intra(r, e["setup"], "backtest", e["entry_price"], exit_price=e["exit_price"],
                              result=e["result"], profit=profit_units(e["result"], r.payout or 0.0))

    def _poll(self, broker: Broker) -> None:
        for r in list(self.runners.values()):
            if r.ready:
                self._poll_runner(broker, r)
        changed = False
        with self._lock:
            now = self._now()
            for ap in self.approvals:
                if ap["status"] == "disparou" and now > ap["deadline"] + 1:
                    self._close_approval(ap, "expirou sem resposta")
                    changed = True
                elif ap["status"] in ("aguardando", "aprovado") and now > ap["deadline"] + 3:
                    self._close_approval(ap, "não disparou")
                    changed = True
        if changed:
            self.hub.publish({"type": "armed", "status": self.snapshot()})

    def _poll_runner(self, broker: Broker, r: AssetRunner) -> None:
        updates = broker.stream_candles(r.asset, r.timeframe)
        if updates:  # o stream devolve sempre as últimas velas: só conta como vivo se algo mudou
            last = updates[-1]
            sig = (last.ts, last.open, last.high, last.low, last.close)
            if sig != r.last_sig:
                r.last_sig, r.last_data, r.stream_restarted = sig, time.monotonic(), False
        closed: list[Candle] = []
        with self._lock:
            for c in updates:
                closed += r.store.ingest(c)
        now = broker.server_time()
        self._tick_clock(now)
        if not closed:
            with self._lock:
                closed += r.store.close_forming_if_expired(now - STREAM_GRACE_SECONDS)
        if closed:
            r.tradable = broker.tradable(r.asset)  # antes de abrir pedidos de aprovação para a próxima vela
            fresh = broker.payout_now(r.asset)  # o payout muda ao longo do dia (filtro de payout mínimo)
            if fresh:
                r.payout = fresh
        for c in closed:
            self._on_close(r, c)
        forming = r.store.forming
        if forming is not None and r.armed:
            self._check_triggers(r, forming, now)
        if forming is not None and forming != r.last_forming:
            r.last_forming = forming
            self.hub.publish({"type": "tick", "asset": r.asset, "candle": candle_dict(forming)})

    def _on_close(self, r: AssetRunner, candle: Candle) -> None:
        with self._lock:
            step = r.engine.process(candle)
            r.last_step = step
            for a in r.armed:  # setup que não disparou na vela que acabou de fechar
                self._log_armed(r, a, "não acionado")
                self._finish_for(r, a, "não disparou")
            plan = plan_all(r.intra, step, r.engine)
            r.armed, r.plan_reasons = list(plan.armed), list(plan.reasons)
            r.gap_checked = {k for k in r.gap_checked if k[0] > candle.ts}
            new = [s.evaluate_last(r.store.closed) for s in r.strategies]
            opened = self._open_approvals(r, r.armed, candle.ts + r.timeframe)
        self.db.save_candles(r.asset, r.timeframe, [candle])
        self._resolve_pending(r, candle)
        for sig in new:
            if sig is not None and sig.ts == candle.ts:
                row = self._store_signal(r, sig, origin="ao_vivo")
                if row:
                    self.hub.publish({"type": "signal", "signal": row})
        self.hub.publish({"type": "closed", "asset": r.asset, "candle": candle_dict(candle), "status": self.snapshot()})
        if opened:
            self.hub.publish({"type": "approval", "status": self.snapshot()})

    def _check_triggers(self, r: AssetRunner, forming: Candle, now: float) -> None:
        """Gatilho de dentro da vela: disparou nos primeiros 15 s da vela de entrada?"""
        changed = False
        with self._lock:
            for a in list(r.armed):
                if forming.ts > a.target_ts:
                    r.armed.remove(a)
                    self._log_armed(r, a, "não acionado")
                    self._finish_for(r, a, "não disparou")
                    changed = True
                    continue
                if forming.ts != a.target_ts:
                    continue
                if a.key not in r.gap_checked:
                    r.gap_checked.add(a.key)
                    if not gap_ok(a, forming.open):
                        r.armed.remove(a)
                        self._log_armed(r, a, "cancelado: GAP na abertura")
                        self._finish_for(r, a, "cancelado: GAP na abertura")
                        changed = True
                        continue
                    ap = self._approval_for(r, a)
                    if ap is not None:
                        ap["open_price"] = forming.open
                    if a.open_offset is not None:  # marcação medida a partir da abertura real
                        a.level_price = a.level_for_open(forming.open)
                        if ap is not None:
                            ap["level_price"] = a.level_price
                    changed = True
                if now - a.target_ts > a.window_seconds + 1:
                    r.armed.remove(a)
                    self._log_armed(r, a, f"não buscou a marcação nos {a.window_seconds} s")
                    self._finish_for(r, a, "não disparou")
                    changed = True
                    continue
                if touched(a, forming.low, forming.high):
                    r.armed.remove(a)
                    self._log_armed(r, a, "ENTROU")
                    changed = True
                    row = self._store_intra(r, a, "ao_vivo", forming.close)
                    if row:
                        self.hub.publish({"type": "signal", "signal": row})
                    ap = self._approval_for(r, a)
                    if ap is not None:
                        ap["trigger_price"] = forming.close
                        ap["triggered_at"] = now
                        ap["signal_id"] = row["id"] if row else None
                        if ap["status"] == "aprovado":
                            self._send_order(ap, forming.close)
                        elif ap["status"] == "aguardando":
                            ap["status"] = "disparou"
        if changed:
            self.hub.publish({"type": "armed", "status": self.snapshot()})

    def _log_armed(self, r: AssetRunner, a: ArmedSetup, outcome: str) -> None:
        self.armed_log.appendleft({"target_ts": a.target_ts, "asset": r.asset, "direction": a.direction.value,
                                   "strategy": a.strategy, "setup": a.setup_label, "level_price": a.level_price,
                                   "outcome": outcome})

    # ------------------------------------------------------------------ aprovação

    def _tick_clock(self, server_now: float) -> None:
        self._clock = (server_now, time.monotonic())

    def _now(self) -> float:
        if self._clock is None:
            return time.time()
        server, mono = self._clock
        return server + (time.monotonic() - mono)

    def _approval_for(self, r: AssetRunner, a: ArmedSetup) -> dict | None:
        for ap in self.approvals:
            if (ap["asset"], ap["strategy"], ap["target_ts"], ap["direction"]) == (r.asset, a.strategy, a.target_ts, a.direction.value):
                return ap
        return None

    def _order_candidates(self, r: AssetRunner, armed: list[ArmedSetup], now: float) -> list[ArmedSetup]:
        """Uma ordem por par e vela. Entre as estratégias que operam, CALL e PUT juntos se anulam; no mesmo
        sentido, vale a de mais confluências (no empate, a primeira). As outras continuam sendo avaliadas."""
        wanted = [a for a in armed if a.strategy in self.order_strategies and a.target_ts + a.window_seconds > now]
        if len({a.direction for a in wanted}) > 1:
            for a in wanted:
                self._log_armed(r, a, "sem ordem: CALL e PUT ao mesmo tempo")
            return []
        if len(wanted) < 2:
            return wanted
        best = max(wanted, key=lambda a: a.score)
        for a in wanted:
            if a is not best:
                self._log_armed(r, a, "sem ordem: outra estratégia ficou com a entrada desta vela")
        return [best]

    def _open_approvals(self, r: AssetRunner, armed: list[ArmedSetup], now: float) -> list[dict]:
        """Um pedido por par e vela. Nos modos automáticos ele já nasce aprovado (no "com veto",
        aparece na tela e você pode cancelar antes do gatilho)."""
        if self.mode not in ORDER_MODES:
            return []
        auto = self.mode in ("automatico", "automatico_veto")
        opened = []
        for a in self._order_candidates(r, armed, now):
            if any(ap["asset"] == r.asset and ap["target_ts"] == a.target_ts for ap in self.approvals):
                continue
            if not r.tradable[0]:
                self._log_armed(r, a, f"sem ordem: {r.tradable[1]}")
                continue
            block = self.filters.entry_block(r.payout, a.target_ts)
            if block:  # o sinal continua valendo para a estatística; só não vira pedido nem ordem
                self._log_armed(r, a, f"sem ordem: {block}")
                continue
            ap = {"id": next(self._approval_seq), "asset": r.asset, "timeframe": r.timeframe, "strategy": a.strategy,
                  "direction": a.direction.value, "setup": a.setup_label, "level_price": a.level_price,
                  "target_ts": a.target_ts, "deadline": a.target_ts + a.window_seconds, "window_seconds": a.window_seconds,
                  "status": "aprovado" if auto else "aguardando", "auto": auto, "veto": self.mode == "automatico_veto",
                  "open_price": None, "created_at": now, "trigger_price": None, "triggered_at": None,
                  "signal_id": None, "order_id": None, "note": None,
                  "excerpt": [candle_dict(c) for c in r.store.closed[-EXCERPT_CANDLES:]],
                  "overlay": ldp_overlay(r.store.closed, max(0, len(r.store.closed) - EXCERPT_CANDLES), a.target_ts)}
            self.approvals.append(ap)
            opened.append(ap)
        done = [ap for ap in self.approvals if ap["status"] not in OPEN_APPROVAL]
        if len(done) > APPROVALS_KEPT:
            drop = {id(ap) for ap in done[:-APPROVALS_KEPT]}
            self.approvals = [ap for ap in self.approvals if id(ap) not in drop]
        return opened

    def _finish_for(self, r: AssetRunner, a: ArmedSetup, outcome: str) -> None:
        ap = self._approval_for(r, a)
        if ap is not None and ap["status"] in ("aguardando", "aprovado"):
            self._close_approval(ap, outcome)

    def _close_approval(self, ap: dict, outcome: str) -> None:
        ap["status"] = outcome
        ap["excerpt"] = ap["overlay"] = None  # trecho do gráfico só enquanto está aberto

    @staticmethod
    def _approval_view(ap: dict) -> dict:
        return dict(ap)

    def decide(self, approval_id: int, approve: bool) -> dict:
        """Resposta do painel a um pedido de aprovação."""
        with self._lock:
            ap = next((x for x in self.approvals if x["id"] == approval_id), None)
            if ap is None:
                raise KeyError(approval_id)
            if not approve:
                if ap["status"] not in OPEN_APPROVAL:
                    raise ValueError(f"Esta entrada já foi encerrada ({ap['status']}).")
                self._close_approval(ap, "cancelado por você" if ap["status"] == "aprovado" else "rejeitado")
            elif ap["status"] not in ("aguardando", "disparou"):
                raise ValueError(f"Esta entrada já foi encerrada ({ap['status']}).")
            elif ap["status"] == "aguardando":
                ap["status"] = "aprovado"
            else:  # o gatilho já disparou: entra no preço do momento, se ainda estiver na janela
                if self._now() > ap["deadline"] + 1:
                    self._close_approval(ap, "expirou sem resposta")
                    raise ValueError(f"A janela de {ap['window_seconds']} s já fechou: ordem não enviada.")
                r = self.runners.get(ap["asset"])
                forming = r.store.forming if r and r.store else None
                self._send_order(ap, forming.close if forming else ap["trigger_price"])
            view = self._approval_view(ap)
        self.hub.publish({"type": "armed", "status": self.snapshot()})
        return view

    def _send_order(self, ap: dict, price: float | None) -> None:
        r = self.runners.get(ap["asset"])
        payout = (r.payout if r else None) or self.settings.default_payout
        block = self.filters.entry_block(payout, ap["target_ts"])  # o payout pode ter caído desde o pedido
        if block:
            self._close_approval(ap, "bloqueada")
            ap["note"] = block
            return
        order = self.orders.submit(asset=ap["asset"], timeframe=ap["timeframe"], strategy=ap["strategy"],
                                   direction=ap["direction"], ref_price=price, signal_id=ap.get("signal_id"), payout=payout)
        ap["order_id"] = order["id"]
        if order["status"] == "bloqueada":
            self._close_approval(ap, "bloqueada")
            ap["note"] = order.get("error")
        else:
            self._close_approval(ap, "ordem enviada")

    # ------------------------------------------------------------------ resultados (paper)

    def _resolve_from_history(self, r: AssetRunner, candles: list[Candle]) -> None:
        """Sinais que ficaram pendentes numa sessão anterior: avalia com o histórico, se a vela existir."""
        by_ts = {c.ts: c for c in candles}
        for p in self.db.pending_signals(r.asset, r.timeframe):
            c = by_ts.get(p["entry_ts"])
            if c is not None:
                entry = p["entry_price"] if p["entry_price"] is not None else c.open
                result = judge(p["direction"], entry, c.close)
                self.db.resolve_signal(p["id"], entry=entry, exit_=c.close, result=result, profit=profit_units(result, p["payout"]))

    def _resolve_pending(self, r: AssetRunner, candle: Candle) -> None:
        for p in self.db.pending_signals(r.asset, r.timeframe):
            if p["entry_ts"] != candle.ts:
                continue  # velas que o stream perdeu: o resolvedor busca no histórico da IQ
            entry = p["entry_price"] if p["entry_price"] is not None else candle.open
            result = judge(p["direction"], entry, candle.close)
            profit = profit_units(result, p["payout"])
            if self.db.resolve_signal(p["id"], entry=entry, exit_=candle.close, result=result, profit=profit):
                p.update(entry_price=entry, exit_price=candle.close, result=result, profit=profit)
                self.hub.publish({"type": "result", "signal": p})

    def _base_fields(self, r: AssetRunner, origin: str) -> dict:
        return {
            "session_id": r.session_id,
            "origin": origin,
            "asset": r.asset,
            "timeframe": r.timeframe,
            "is_otc": is_otc(r.asset),
            "payout": r.payout or self.settings.default_payout,
            "result": "pendente",
        }

    def _store_signal(self, r: AssetRunner, sig: Signal, origin: str, **extra) -> dict | None:
        fields = self._base_fields(r, origin) | {
            "strategy": sig.strategy,
            "direction": sig.direction.value,
            "setup": sig.setup,
            "candle_ts": sig.ts,
            "entry_ts": sig.ts + r.timeframe,
            "details": sig.details,
        }
        fields.update(extra)
        return self.db.add_signal(**fields)

    def _store_intra(self, r: AssetRunner, a: ArmedSetup, origin: str, entry_price: float, **extra) -> dict | None:
        fields = self._base_fields(r, origin) | {
            "strategy": a.strategy,
            "direction": a.direction.value,
            "setup": a.setup_label,
            "candle_ts": a.decision_ts,
            "entry_ts": a.target_ts,
            "entry_price": entry_price,
            "details": a.to_dict() | {"intravela": True},
        }
        fields.update(extra)
        return self.db.add_signal(**fields)

    def _set_status(self, status: str) -> None:
        with self._lock:
            self.status = status
        self.hub.publish({"type": "status", **self.snapshot()})
