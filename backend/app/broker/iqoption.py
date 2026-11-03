"""Adaptador da IQ Option usando a biblioteca NÃO OFICIAL `iqoptionapi`.

Avisos:
- A biblioteca é engenharia reversa do site e está sem atualização desde jan/2022. Ela pode
  parar de funcionar quando a IQ Option muda algo, e o uso automatizado pode violar os
  termos da corretora (risco de bloqueio da conta). Por isso tudo começa em PRACTICE.
- Instalação (no venv do backend):
    pip install websocket-client==0.56
    pip install -U https://github.com/iqoptionapi/iqoptionapi/archive/refs/heads/master.zip
- A biblioteca espera respostas da IQ em laços SEM prazo e captura até o Ctrl+C. Por isso
  toda chamada a ela passa por `_call()`, que roda numa thread com prazo máximo e vira
  BrokerError se a IQ não responder a tempo.
- `get_candles` tem atraso de ~30 s para a vela atual; ao vivo, use o stream.
- Ordens: binária turbo de 1 min (`buy`), com vencimento no fim do minuto atual se faltarem
  mais de 30 s. REAL continua bloqueada sem IQ_ALLOW_REAL=true.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any, TypeVar

from app.broker.base import AccountType, Broker, BrokerError, OrderResult, OrderTicket, expiry_for
from app.market.candle import Candle
from app.paper import DRAW, LOSS, WIN

log = logging.getLogger(__name__)

MAX_CANDLES_PER_REQUEST = 1000
INSTRUMENTS_TTL = 600  # segundos até recarregar a lista de binárias (horários e payouts mudam)
T = TypeVar("T")


def _order_result(win: str | None, win_amount: float, amount: float) -> OrderResult | None:
    if win == "win":
        return OrderResult(WIN, round(win_amount - amount, 2))
    if win in ("loose", "lose", "loss"):
        return OrderResult(LOSS, -amount)
    if win == "equal":
        return OrderResult(DRAW, 0.0)
    return None


def _to_candle(raw: dict[str, Any]) -> Candle:
    return Candle(
        ts=int(raw["from"]),
        open=float(raw["open"]),
        high=float(raw["max"]),
        low=float(raw["min"]),
        close=float(raw["close"]),
        volume=float(raw.get("volume") or 0.0),
    )


def call_with_deadline(label: str, fn: Callable[[], T], timeout: float) -> T:
    """Roda `fn` numa thread e espera no máximo `timeout` segundos.

    Se estourar o prazo, levanta BrokerError (a thread presa morre junto com o processo).
    O Ctrl+C continua funcionando porque quem espera é a thread principal.
    """
    box: dict[str, Any] = {}

    def run() -> None:
        try:
            box["result"] = fn()
        except BaseException as exc:  # noqa: BLE001 - repassado para a thread principal
            box["error"] = exc

    worker = threading.Thread(target=run, name=f"iq-{label}", daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        raise BrokerError(f"A IQ Option não respondeu a '{label}' em {timeout:.0f}s")
    if "error" in box:
        raise box["error"]
    return box["result"]


class IQOptionBroker(Broker):
    def __init__(
        self,
        email: str,
        password: str,
        allow_real: bool = False,
        request_pause: float = 0.3,
        sms_code_provider: Callable[[], str] | None = None,
        call_timeout: float = 20.0,
    ) -> None:
        if not email or not password:
            raise BrokerError("Preencha IQ_EMAIL e IQ_PASSWORD no arquivo backend/.env")
        self._email = email
        self._password = password
        self._allow_real = allow_real
        self._pause = request_pause
        self._sms_code_provider = sms_code_provider
        self._timeout = call_timeout
        self._api: Any = None
        self._account = AccountType.PRACTICE
        # A biblioteca guarda a resposta de get_candles num lugar só: dois pedidos ao mesmo tempo se misturam.
        self._history_lock = threading.Lock()
        # O mesmo vale para a compra (a resposta vai para um dicionário que cada compra zera).
        self._buy_lock = threading.Lock()
        self._instruments: dict[str, dict] = {}
        self._instruments_at = 0.0
        self._skew_warned = False

    def _call(self, label: str, fn: Callable[[], T], timeout: float | None = None) -> T:
        return call_with_deadline(label, fn, self._timeout if timeout is None else timeout)

    # ------------------------------------------------------------------ conexão

    def connect(self) -> None:
        try:
            from iqoptionapi.stable_api import IQ_Option
        except ImportError as exc:  # pragma: no cover - depende de instalação manual
            raise BrokerError(
                "Biblioteca iqoptionapi não instalada. Veja as instruções no topo de app/broker/iqoption.py"
            ) from exc
        self._api = IQ_Option(self._email, self._password)
        ok, reason = self._call("login", self._api.connect, timeout=45)
        if not ok and reason == "2FA":
            if self._sms_code_provider is None:
                raise BrokerError("A conta pede código SMS (2FA). Rode a ferramenta em modo interativo.")
            code = self._sms_code_provider()  # input() fica na thread principal
            ok, reason = self._call("login 2FA", lambda: self._api.connect_2fa(code), timeout=45)
        if not ok:
            raise BrokerError(f"Falha no login da IQ Option: {reason}")
        self.set_account(self._account)
        self._load_instruments()
        self._start_refresher()
        log.info("Conectado à IQ Option (conta %s, %d instrumentos de binária)", self._account.value, len(self._instruments))

    def _start_refresher(self) -> None:
        """Recarrega horários e payouts em segundo plano: a leitura do mercado nunca espera por isso."""
        api = self._api

        def loop() -> None:
            while self._api is api:
                time.sleep(INSTRUMENTS_TTL)
                if self._api is api:
                    self._load_instruments()

        threading.Thread(target=loop, name="iq-instrumentos", daemon=True).start()

    def currency(self) -> str:
        try:
            return str(self._call("moeda", self._api.get_currency, timeout=10) or "USD")
        except BrokerError:
            return "USD"

    # ------------------------------------------------------------------ instrumentos de binária

    def _load_instruments(self) -> None:
        """Lista de binárias da conta. Os pares normais aparecem como "EURUSD-op" (id próprio, preço
        um pouco diferente do "EURUSD" antigo da biblioteca): registra esses nomes para velas, stream e ordens."""
        from iqoptionapi import constants as op_code

        try:
            init = self._call("instrumentos", self._api.get_all_init_v2, timeout=30)
        except BrokerError as exc:
            log.warning("Lista de instrumentos indisponível: %s", exc)
            return
        found: dict[str, dict] = {}
        for kind in ("binary", "turbo"):  # turbo por último: é a de 1 minuto
            for aid, a in ((init or {}).get(kind) or {}).get("actives", {}).items():
                name = str(a.get("name", "")).split(".")[-1]
                if not name:
                    continue
                op_code.ACTIVES.setdefault(name, int(aid))
                commission = ((a.get("option") or {}).get("profit") or {}).get("commission")
                found[name] = {
                    "id": int(aid), "kind": kind, "enabled": bool(a.get("enabled")), "suspended": bool(a.get("is_suspended")),
                    "schedule": a.get("schedule") or [],
                    "payout": (100 - commission) / 100 if commission is not None else None,
                }
        if found:
            self._instruments, self._instruments_at = found, time.time()

    def _instrument(self, asset: str) -> dict | None:
        return self._instruments.get(asset)

    def tradable(self, asset: str) -> tuple[bool, str]:
        """Dá para comprar binária de 1 min neste ativo agora?"""
        info = self._instrument(asset)
        if info is None:
            return False, f"{asset} não está na lista de binárias da IQ (pares normais terminam em -op, ex.: EURUSD-op)"
        if info["kind"] != "turbo":
            return False, f"{asset} não tem binária de 1 minuto"
        now = self.server_time()
        if not info["enabled"] or info["suspended"] or not any(s[0] <= now <= s[1] for s in info["schedule"]):
            return False, f"{asset} está fechado para binária agora"
        return True, "ok"

    def disconnect(self) -> None:
        if self._api is None:
            return
        try:
            self._call("desconectar", self._api.api.close, timeout=5)
        except Exception as exc:  # noqa: BLE001 - ao trocar de login, uma conexão que não fecha não importa
            log.debug("Conexão antiga não fechou: %s", exc)
        self._api = None

    def is_connected(self) -> bool:
        return self._api is not None and bool(self._call("checar conexão", self._api.check_connect, timeout=5))

    def ensure_connected(self, attempts: int = 3) -> None:
        for attempt in range(1, attempts + 1):
            if self.is_connected():
                return
            log.warning("Sem conexão com a IQ Option; tentativa %d de %d", attempt, attempts)
            try:
                self.connect()
            except BrokerError as exc:
                log.warning("Reconexão falhou: %s", exc)
            time.sleep(2 * attempt)
        if not self.is_connected():
            raise BrokerError("Não foi possível reconectar à IQ Option")

    def set_account(self, account: AccountType) -> None:
        if account is AccountType.REAL and not self._allow_real:
            raise BrokerError("Conta REAL bloqueada. Só libere (IQ_ALLOW_REAL=true) depois da validação em demo.")
        self._account = account
        if self._api is not None:
            # O valor vem do enum: a biblioteca encerra o processo (exit) se receber um nome inválido.
            self._call("trocar conta", lambda: self._api.change_balance(account.value))

    @property
    def account(self) -> AccountType:
        return self._account

    def balance(self) -> float:
        value = self._call("saldo", self._api.get_balance)
        if value is None:
            raise BrokerError("Não foi possível ler o saldo")
        return float(value)

    def server_time(self) -> float:
        return float(self._call("horário do servidor", self._api.get_server_timestamp, timeout=5))

    # ------------------------------------------------------------------ velas

    def get_candles(self, asset: str, timeframe: int, count: int, end_ts: float | None = None) -> list[Candle]:
        with self._history_lock:
            return self._get_candles(asset, timeframe, count, end_ts)

    def _require_known(self, asset: str) -> None:
        from iqoptionapi import constants as op_code

        if asset not in op_code.ACTIVES:
            raise BrokerError(f"Ativo {asset!r} não existe na IQ Option (pares de binária terminam em -op, ex.: EURUSD-op)")

    def _get_candles(self, asset: str, timeframe: int, count: int, end_ts: float | None) -> list[Candle]:
        self._require_known(asset)
        end = end_ts if end_ts is not None else self.server_time()
        collected: dict[int, Candle] = {}
        remaining = count
        while remaining > 0:
            batch = min(remaining, MAX_CANDLES_PER_REQUEST)
            batch_end = end
            raw = self._call(f"histórico {asset}", lambda: self._api.get_candles(asset, timeframe, batch, batch_end))
            if raw is None:
                raise BrokerError(f"Ativo {asset!r} não encontrado na IQ Option")
            if not raw:
                break
            for item in raw:
                candle = _to_candle(item)
                collected[candle.ts] = candle
            remaining -= len(raw)
            end = min(int(item["from"]) for item in raw) - 1
            time.sleep(self._pause)
        now = self.server_time()
        closed = [c for c in collected.values() if c.ts + timeframe <= now]
        return sorted(closed, key=lambda c: c.ts)[-count:]

    def start_stream(self, asset: str, timeframe: int, buffer: int = 10) -> None:
        self._require_known(asset)
        self._call(f"iniciar stream {asset}", lambda: self._api.start_candles_stream(asset, timeframe, buffer), timeout=30)

    def stop_stream(self, asset: str, timeframe: int) -> None:
        self._call(f"parar stream {asset}", lambda: self._api.stop_candles_stream(asset, timeframe), timeout=10)

    def stream_candles(self, asset: str, timeframe: int) -> list[Candle]:
        raw = self._call(f"stream {asset}", lambda: self._api.get_realtime_candles(asset, timeframe), timeout=5)
        if not raw:
            return []
        candles = [_to_candle(item) for item in list(raw.values())]
        return sorted(candles, key=lambda c: c.ts)

    # ------------------------------------------------------------------ ordens

    def buy(self, asset: str, direction: str, amount: float, minutes: int = 1) -> OrderTicket:
        if self._account is AccountType.REAL and not self._allow_real:
            raise BrokerError("Conta REAL bloqueada: ordem não enviada.")
        if direction not in ("call", "put"):
            raise BrokerError(f"Direção inválida: {direction!r}")
        if amount <= 0:
            raise BrokerError("Valor da entrada precisa ser maior que zero")
        ok_now, why = self.tradable(asset)
        if not ok_now:
            raise BrokerError(why)
        server = self.server_time()
        skew = time.time() - server
        if abs(skew) > 3 and not self._skew_warned:
            # Não afeta a ordem (o vencimento vai calculado pelo horário da IQ), mas fica registrado.
            log.warning("Relógio do computador %+.1fs fora do horário da IQ", skew)
            self._skew_warned = True
        expected = expiry_for(server, minutes)
        with self._buy_lock:
            # Vencimento explícito: a compra normal da biblioteca calcula pelo relógio LOCAL e erra a vela.
            ok, order_id = self._call(
                f"ordem {asset}",
                lambda: self._api.buy_by_raw_expirations(float(amount), asset, direction, "turbo", expected),
                timeout=12,
            )
        if not ok or not isinstance(order_id, int):
            raise BrokerError(f"A IQ recusou a ordem: {order_id or 'sem resposta'}")
        log.info("Ordem %s %s %s %.2f enviada (id %s, vence %s)", self._account.value, asset, direction, amount, order_id, expected)
        return OrderTicket(order_id=order_id, asset=asset, direction=direction, amount=float(amount),
                           account=self._account.value, opened_at=server, expires_at=expected)

    def order_result(self, ticket: OrderTicket) -> OrderResult | None:
        """Lê os avisos que a IQ manda sozinha quando a opção fecha (nada aqui espera resposta)."""
        api = self._api.api
        msg = (getattr(api, "socket_option_closed", {}) or {}).get(ticket.order_id)
        if msg is not None:
            m = msg.get("msg", {})
            return _order_result(m.get("win"), float(m.get("win_amount") or 0.0), float(m.get("sum") or ticket.amount))
        closed = (getattr(api, "order_binary", {}) or {}).get(ticket.order_id)  # aviso "option-closed"
        if closed:
            res = closed.get("result") or closed.get("win")
            win_amount = closed.get("profit_amount", closed.get("win_amount"))
            if res is not None and win_amount is not None:
                return _order_result(res, float(win_amount), float(closed.get("amount") or ticket.amount))
        return None

    # ------------------------------------------------------------------ ativos

    def open_assets(self, option_type: str = "turbo") -> dict[str, bool]:
        # Chamada pesada (a própria biblioteca avisa); use com moderação.
        data = self._call("ativos abertos", self._api.get_all_open_time, timeout=60)
        return {asset: bool(info.get("open")) for asset, info in data.get(option_type, {}).items()}

    def payouts(self, option_type: str = "turbo") -> dict[str, float]:
        if self._instruments:
            return {name: info["payout"] for name, info in self._instruments.items()
                    if info["kind"] == option_type and info["payout"] is not None}
        data = self._call("payouts", self._api.get_all_profit, timeout=30)
        out: dict[str, float] = {}
        for asset, info in data.items():
            value = info.get(option_type) if isinstance(info, dict) else None
            if value is not None:
                out[asset] = float(value)
        return out
