"""Adaptador da IQ Option usando a biblioteca NÃO OFICIAL `iqoptionapi`.

Avisos:
- A biblioteca é engenharia reversa do site e está sem atualização desde jan/2022. Ela pode
  parar de funcionar quando a IQ Option muda algo, e o uso automatizado pode violar os
  termos da corretora (risco de bloqueio da conta). Por isso tudo começa em PRACTICE.
- Instalação (no venv do backend):
    pip install websocket-client==0.56
    pip install -U https://github.com/iqoptionapi/iqoptionapi/archive/refs/heads/master.zip
- A biblioteca espera respostas da IQ em laços SEM prazo e SEM pausa (`while x == None: pass`),
  e captura até o Ctrl+C. Por isso toda chamada a ela passa por `_call()`, que roda numa thread
  com prazo máximo, vira BrokerError se a IQ não responder a tempo e encerra a thread presa
  (senão ela gastaria CPU para sempre e, somando várias, travaria o processo inteiro).
- A biblioteca guarda a sessão numa variável global e tenta reaproveitá-la no próximo login. Com a
  sessão vencida, a IQ fecha a conexão e o login fica esperando para sempre: `connect()` limpa antes.
- `get_candles` tem atraso de ~30 s para a vela atual; ao vivo, use o stream.
- Ordens: binária turbo ou digital de 1 min (`buy`), com vencimento no fim do minuto atual se faltarem
  mais de 30 s, calculado pelo horário da IQ. REAL continua bloqueada sem IQ_ALLOW_REAL=true.
- Digital: a binária e a digital usam o mesmo ativo (mesmo id e mesmo preço). A lista de digitais vem do
  pedido novo da IQ (o da biblioteca deixou de ser respondido), o payout dela vem da assinatura
  "top-assets-updated" (todos os pares numa mensagem, a cada ~10 s) e o resultado, do aviso "position-changed".
"""

from __future__ import annotations

import ctypes
import logging
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, TypeVar

from app.broker.base import (
    BINARY,
    DIGITAL,
    DIGITAL_MINUTES,
    AccountType,
    Broker,
    BrokerError,
    OrderRefused,
    OrderResult,
    OrderTicket,
    digital_expiry_for,
    expiry_for,
)
from app.market.candle import Candle, is_otc, normalize_asset, valid_asset
from app.paper import DRAW, LOSS, WIN

log = logging.getLogger(__name__)

MAX_CANDLES_PER_REQUEST = 1000
INSTRUMENTS_TTL = 120  # segundos até recarregar a lista de binárias (horários e payouts mudam; ler leva ~1 s)
DIGITAL_TIMEOUT = 15  # sem resposta, segue sem digital e tenta de novo depois
DIGITAL_RETRY_SECONDS = 300  # a IQ não respondeu a lista de digitais: não insiste antes disso
# O pedido antigo da biblioteca ("get-underlying-list" 2.0) deixou de ser respondido ("Invalid contract").
DIGITAL_LIST_REQUEST = {"name": "digital-option-instruments.get-underlying-list", "version": "3.0",
                        "body": {"filter_suspended": True}}
DIGITAL_PAYOUT_STALE = 90  # payout da digital sem atualização há isso (chega a cada ~10 s): assina de novo
DIGITAL_PAYOUT_DEAD = 180  # e, sem nada há isso, a digital fica sem payout (o bot não compra no escuro)
# A IQ recusou a digital de um par ("invalid instrument"): o bot não tenta a digital nele por esse tempo.
DIGITAL_REFUSED_SECONDS = 6 * 3600
MAX_TURBO_MINUTES = 5  # a partir de 15 min é outro produto, com outro payout
CATEGORIES = (("forex", "Moedas"), ("crypto", "Cripto"), ("equities", "Ações"), ("indices", "Índices"))
DIGITAL_CATEGORIES = {"Forex": "Moedas", "Crypto": "Cripto", "Stock": "Ações", "Index": "Índices"}
CLOCK_FROZEN_SECONDS = 60  # o horário da IQ chega pelo websocket: parado por isso = conexão morta
MAX_STUCK_CALLS = 6  # chamadas que nem à força encerraram (presas em rede): daqui em diante a conexão é dada como travada
REAP_SECONDS = 0.5
MOOD_INSTRUMENT = "turbo-option"  # o sentimento da binária de 1 a 5 min (o que aparece na tela da IQ)
T = TypeVar("T")


class _StampedMood(dict):
    """Fica no lugar do `traders_mood` da biblioteca, que é um dicionário da CLASSE (o mesmo para todas as
    conexões e sem horário): cada conexão ganha o seu e cada valor guarda quando chegou."""

    def __init__(self) -> None:
        super().__init__()
        self.at: dict[int, float] = {}

    def __setitem__(self, key: int, value: object) -> None:
        self.at[key] = time.monotonic()
        super().__setitem__(key, value)


def _category(group: str) -> str:
    return next((label for key, label in CATEGORIES if key in group), "Outros")


def _schedule_edges(schedule: list, now: float) -> tuple[float | None, float | None]:
    """(próxima abertura, próximo fechamento) pela grade de horários da IQ. Intervalos encostados contam
    como um só (a grade costuma vir dividida por dia)."""
    spans = sorted((float(s[0]), float(s[1])) for s in schedule if len(s) >= 2)
    for i, (start, end) in enumerate(spans):
        if start <= now <= end:
            for nxt_start, nxt_end in spans[i + 1:]:
                if nxt_start > end + 60:
                    break
                end = max(end, nxt_end)
            return None, end
    upcoming = [start for start, _ in spans if start > now]
    return (min(upcoming) if upcoming else None), None


def _parse_digital(items: object) -> dict[str, dict]:
    """Lista de opções digitais da IQ -> {nome: id, horários e estado}. Ignora o que não reconhece.
    Os nomes são os mesmos da binária ("EURUSD-op", "EURUSD-OTC"), com o mesmo id de ativo."""
    found: dict[str, dict] = {}
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        name = normalize_asset(str(item.get("underlying") or ""))
        if not valid_asset(name):
            continue
        schedule = [(float(s["open"]), float(s["close"])) for s in item.get("schedule") or []
                    if isinstance(s, dict) and s.get("open") is not None and s.get("close") is not None]
        active_id = item.get("active_id")
        found[name] = {"schedule": schedule, "enabled": item.get("is_enabled", True) is not False,
                       "suspended": bool(item.get("is_suspended")), "label": str(item.get("name") or name),
                       "id": int(active_id) if isinstance(active_id, int) else None,
                       "category": DIGITAL_CATEGORIES.get(str(item.get("active_type")), "Outros")}
    return found


def _parse_digital_payouts(items: object) -> dict[int, float]:
    """Mensagem "top-assets-updated" da digital -> {id do ativo: payout em fração}. Payout zero = sem digital agora."""
    out: dict[int, float] = {}
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict) or not isinstance(item.get("active_id"), int):
            continue
        profit = item.get("spot_profit") or {}
        value = profit.get("value") if isinstance(profit, dict) else None
        if isinstance(value, (int, float)) and value > 0 and profit.get("is_valid", True) is not False:
            out[item["active_id"]] = round(float(value) / 100, 4)
    return out


def _balance_entry(raw: object, balance_id: object) -> dict | None:
    """A carteira em uso na resposta "balances" da IQ (a conta real tem o saldo e, separado, o bônus)."""
    items = raw.get("msg") if isinstance(raw, dict) else None
    for item in items if isinstance(items, list) else []:
        if isinstance(item, dict) and item.get("id") == balance_id:
            return item
    return None


def _digital_name(asset: str, digital: dict[str, dict]) -> str | None:
    """Nome da digital do mesmo par. Hoje é o mesmo nome; antes, o normal vinha sem sufixo ("EURUSD")."""
    if asset in digital:
        return asset
    base, _, suffix = asset.partition("-")
    return base if suffix == "op" and base in digital else None


def _digital_open(info: dict, now: float) -> bool:
    return info["enabled"] and not info["suspended"] and any(s[0] <= now <= s[1] for s in info["schedule"])


def _digital_instrument(active_id: int, expires_at: int, minutes: int, direction: str) -> str:
    """Código da digital "no preço atual" (SPT) como a IQ usa hoje: do{id}A{AAAAMMDD}D{HHMM}00T{min}M{C|P}SPT (UTC)."""
    stamp = datetime.fromtimestamp(expires_at, timezone.utc).strftime("%Y%m%d%H%M")
    return f"do{active_id}A{stamp[:8]}D{stamp[8:]}00T{minutes}M{'C' if direction == 'call' else 'P'}SPT"


def _digital_result(msg: dict, amount: float) -> OrderResult | None:
    """Aviso "position-changed" da digital -> resultado, ou None se ainda está aberta."""
    if msg.get("status") != "closed":
        return None
    invest = float(msg.get("invest") or amount)
    if msg.get("close_profit") is not None:
        profit = float(msg["close_profit"]) - invest  # quanto voltou menos o que entrou
    elif msg.get("pnl_realized") is not None:
        profit = float(msg["pnl_realized"])
    else:
        return None
    profit = round(profit, 2)
    if profit > 0:
        return OrderResult(WIN, profit)
    if profit < 0:
        return OrderResult(LOSS, profit)
    return OrderResult(DRAW, 0.0)


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


class _Abandoned(SystemExit):
    """Levantada dentro da thread de uma chamada que estourou o prazo (SystemExit: sai sem traceback no log)."""


_abandoned: list[threading.Thread] = []
_abandoned_lock = threading.Lock()
_reaper_started = False


def _inject(thread: threading.Thread) -> None:
    if thread.ident is not None:
        ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(thread.ident), ctypes.py_object(_Abandoned))


def _reap_loop() -> None:
    # Repete porque a biblioteca tem `except:` soltos que engolem a exceção. Os laços dela têm saída
    # por aqui; o que não sai é quem está preso numa chamada de rede (não gasta CPU e sai quando ela volta).
    while True:
        time.sleep(REAP_SECONDS)
        with _abandoned_lock:
            _abandoned[:] = [t for t in _abandoned if t.is_alive()]
            alive = list(_abandoned)
        for thread in alive:
            _inject(thread)


def _abandon(worker: threading.Thread) -> None:
    """Encerra à força a thread de uma chamada sem resposta."""
    global _reaper_started
    with _abandoned_lock:
        _abandoned.append(worker)
        if not _reaper_started:
            _reaper_started = True
            threading.Thread(target=_reap_loop, name="iq-encerra-presas", daemon=True).start()
    _inject(worker)


def stuck_calls() -> int:
    """Quantas chamadas estouraram o prazo e continuam vivas."""
    with _abandoned_lock:
        _abandoned[:] = [t for t in _abandoned if t.is_alive()]
        return len(_abandoned)


def call_with_deadline(label: str, fn: Callable[[], T], timeout: float) -> T:
    """Roda `fn` numa thread e espera no máximo `timeout` segundos.

    Se estourar o prazo, encerra a thread e levanta BrokerError.
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
        _abandon(worker)
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
        self._digital: dict[str, dict] = {}  # opções digitais por nome; vazio = ainda não leu (ou a IQ não respondeu)
        self._digital_retry_at = 0.0
        # Payout da digital: a última mensagem da IQ (lista), quando chegou e o que ela virou, por nome.
        self._dp_source: object = None
        self._dp_seen = 0.0  # monotonic da última mensagem nova
        self._dp_subscribed = 0.0
        self._dp_by_id: dict[int, float] = {}
        # Par -> (até quando, no horário da IQ; o que a IQ disse). Fica entre reconexões: a recusa é do par, não da conexão.
        self._digital_refused: dict[str, tuple[float, str]] = {}
        self._skew_warned = False
        self._skew: float | None = None  # relógio local - horário da IQ, medido ao conectar
        self._mood_subs: set[str] = set()  # pares com o sentimento assinado NESTA conexão

    def _call(self, label: str, fn: Callable[[], T], timeout: float | None = None) -> T:
        """Toda falha da biblioteca vira BrokerError: o bot trata como problema de conexão (e reconecta)."""
        if self._api is None:
            raise BrokerError(f"Sem conexão com a IQ Option ({label})")
        stuck = stuck_calls()
        if stuck >= MAX_STUCK_CALLS:  # não abre mais threads em cima de uma conexão travada
            raise BrokerError(f"A IQ Option não respondeu a {stuck} chamadas que seguem presas")
        try:
            return call_with_deadline(label, fn, self._timeout if timeout is None else timeout)
        except BrokerError:
            raise
        except Exception as exc:  # noqa: BLE001 - KeyError, websocket etc. de dentro da biblioteca
            raise BrokerError(f"Erro da IQ Option em '{label}': {exc}") from exc

    # ------------------------------------------------------------------ conexão

    def connect(self) -> None:
        try:
            from iqoptionapi import global_value
            from iqoptionapi.stable_api import IQ_Option
        except ImportError as exc:  # pragma: no cover - depende de instalação manual
            raise BrokerError(
                "Biblioteca iqoptionapi não instalada. Veja as instruções no topo de app/broker/iqoption.py"
            ) from exc
        global_value.SSID = None  # sem isso, um login depois de uma queda reaproveita a sessão vencida e trava
        self._api = IQ_Option(self._email, self._password)
        self._mood_subs = set()
        self._skew = None
        try:
            ok, reason = self._call("login", self._api.connect, timeout=45)
            if not ok and reason == "2FA":
                if self._sms_code_provider is None:
                    raise BrokerError("A conta pede código SMS (2FA). Rode a ferramenta em modo interativo.")
                code = self._sms_code_provider()  # input() fica na thread principal
                ok, reason = self._call("login 2FA", lambda: self._api.connect_2fa(code), timeout=45)
            if not ok:
                if "invalid_credentials" in str(reason):  # o código fica na mensagem: o bot usa para não ficar tentando
                    raise BrokerError("A IQ recusou o e-mail ou a senha (invalid_credentials)")
                raise BrokerError(f"Falha no login da IQ Option: {reason}")
            self.set_account(self._account)
        except BrokerError:
            self.disconnect()  # não deixa meia conexão aberta para trás
            raise
        self._skew = time.time() - self.server_time()
        self._load_instruments()
        # Antes de carregar os pares: os que só têm digital precisam do id que vem nesta lista.
        self._digital_retry_at = 0.0
        self._load_digital()
        self._dp_source, self._dp_by_id, self._dp_seen, self._dp_subscribed = None, {}, 0.0, 0.0
        self._subscribe_digital_payouts()
        self._start_refresher()
        log.info("Conectado à IQ Option (conta %s, %d instrumentos de binária, %d de digital)",
                 self._account.value, len(self._instruments), len(self._digital))

    def _start_refresher(self) -> None:
        """Recarrega horários e payouts em segundo plano: a leitura do mercado nunca espera por isso."""
        api = self._api

        def loop() -> None:
            while self._api is api:
                time.sleep(INSTRUMENTS_TTL)
                # Só com a conexão viva: sem ela, a biblioteca tentaria reconectar por conta própria.
                if self._api is api and self.is_connected():
                    self._load_instruments()
                    self._load_digital()
                    if time.monotonic() - max(self._dp_seen, self._dp_subscribed) > DIGITAL_PAYOUT_STALE:
                        self._subscribe_digital_payouts()

        threading.Thread(target=loop, name="iq-instrumentos", daemon=True).start()

    def currency(self) -> str:
        try:
            return str(self._call("moeda", lambda: self._api.get_currency(), timeout=10) or "USD")
        except BrokerError:
            return "USD"

    # ------------------------------------------------------------------ instrumentos de binária

    def _load_instruments(self) -> None:
        """Lista de binárias da conta. Os pares normais aparecem como "EURUSD-op" (id próprio, preço
        um pouco diferente do "EURUSD" antigo da biblioteca): registra esses nomes para velas, stream e ordens."""
        from iqoptionapi import constants as op_code

        try:
            init = self._call("instrumentos", lambda: self._api.get_all_init_v2(), timeout=30)
        except BrokerError as exc:
            log.warning("Lista de instrumentos indisponível: %s", exc)
            return
        found: dict[str, dict] = {}
        groups = (init or {}).get("groups") or {}
        for kind in ("binary", "turbo"):  # turbo por último: é a de 1 minuto
            for aid, a in ((init or {}).get(kind) or {}).get("actives", {}).items():
                name = str(a.get("name", "")).split(".")[-1]
                if not name:
                    continue
                op_code.ACTIVES.setdefault(name, int(aid))
                option = a.get("option") or {}
                commission = (option.get("profit") or {}).get("commission")
                found[name] = {
                    "id": int(aid), "kind": kind, "enabled": bool(a.get("enabled")), "suspended": bool(a.get("is_suspended")),
                    "schedule": a.get("schedule") or [],
                    "payout": (100 - commission) / 100 if commission is not None else None,
                    "label": str(a.get("description") or name).removeprefix("front."),
                    "category": _category(str(groups.get(str(a.get("group_id")), ""))),
                    "min": a.get("minimal_bet"), "max": a.get("maximal_bet"), "count": option.get("count"),
                }
        if found:
            self._instruments, self._instruments_at = found, time.time()

    def _request_digital(self) -> list:
        """Lista de digitais pelo pedido novo da IQ. A resposta ("underlying-list") cai no mesmo lugar do pedido
        antigo da biblioteca."""
        api = self._api.api
        api.underlying_list_data = None
        api.send_websocket_request("sendMessage", DIGITAL_LIST_REQUEST, "lista-digitais")
        while api.underlying_list_data is None:
            time.sleep(0.05)
        data = api.underlying_list_data
        return (data.get("underlying") if isinstance(data, dict) else None) or []

    def _load_digital(self) -> None:
        """Opções digitais da conta (nome, id, horários). Os ids entram na tabela da biblioteca: um par só de digital
        (ex.: USDNOK-OTC) precisa dele para velas e stream."""
        from iqoptionapi import constants as op_code

        if time.monotonic() < self._digital_retry_at:
            return
        try:
            items = self._call("lista de digitais", self._request_digital, timeout=DIGITAL_TIMEOUT)
            found = _parse_digital(items)
        except Exception as exc:  # noqa: BLE001 - sem a lista, o bot segue só com a binária
            log.info("Lista de digitais indisponível (tenta de novo em %d min): %s", DIGITAL_RETRY_SECONDS // 60, exc)
            self._digital_retry_at = time.monotonic() + DIGITAL_RETRY_SECONDS
            return
        if found:
            for name, info in found.items():
                if info["id"] is not None:
                    op_code.ACTIVES.setdefault(name, info["id"])
            self._digital = found  # troca inteira: quem está lendo a lista antiga continua com ela
        elif items:  # a IQ mudou o formato: melhor não mostrar nada do que mostrar "sem digital" em tudo
            log.warning("Lista de digitais num formato desconhecido: %.200r", items)

    def _subscribe_digital_payouts(self) -> None:
        """Assina o payout da digital de todos os pares (a IQ manda a lista inteira a cada ~10 s)."""
        api = self._api
        if api is None:
            return
        self._dp_subscribed = time.monotonic()
        try:
            self._call("payout da digital", lambda: api.api.Subscribe_Top_Assets_Updated("digital-option"), timeout=5)
        except Exception as exc:  # noqa: BLE001 - sem payout, a digital fica fora (a binária continua)
            log.info("Payout da digital indisponível: %s", exc)

    def _digital_payouts(self) -> dict[int, float]:
        """Payout da digital por id de ativo, da última mensagem da IQ. Vazio se nada chegou há muito tempo."""
        api = self._api
        data = getattr(getattr(api, "api", None), "top_assets_updated_data", None) or {}
        raw = data.get("digital-option") if isinstance(data, dict) else None
        if raw is not None and raw is not self._dp_source:  # cada mensagem chega como uma lista nova
            self._dp_source, self._dp_by_id, self._dp_seen = raw, _parse_digital_payouts(raw), time.monotonic()
        if not self._dp_seen or time.monotonic() - self._dp_seen > DIGITAL_PAYOUT_DEAD:
            return {}
        return self._dp_by_id

    def _digital_info(self, asset: str) -> dict | None:
        digital = self._digital
        name = _digital_name(asset, digital)
        return digital.get(name) if name else None

    def _digital_payout(self, info: dict | None) -> float | None:
        return self._digital_payouts().get(info["id"]) if info and info.get("id") is not None else None

    def _digital_closed_reason(self, asset: str, info: dict | None, now: float, payout: float | None) -> str | None:
        if info is None:
            return (f"{asset} não tem opção digital" if self._digital
                    else f"{asset}: a lista de digitais da IQ ainda não chegou")
        refused = self._digital_refused.get(asset)
        if refused and now < refused[0]:
            again = datetime.fromtimestamp(refused[0]).strftime("%H:%M")
            return f"a IQ recusou a digital de {asset} ({refused[1]}): o bot só tenta de novo às {again}"
        if not _digital_open(info, now):
            return f"{asset} está fechado para digital agora"
        if not is_otc(asset):
            # Mercado normal: a lista da IQ diz que a digital está aberta mesmo com a binária do par fechada, mas aí
            # ela recusa a compra ("invalid instrument"). Em 09/11/2026 foram 10 de 10 recusas assim, e as digitais
            # que entraram no mercado normal tinham a binária aberta. Fechado aqui, o par fica no OTC.
            binary = self._instrument(asset)
            if binary is None or binary["kind"] != "turbo" or self._closed_reason(asset, binary, now):
                return f"{asset}: a digital do mercado normal só vale com a binária do par aberta"
        if payout is None:
            return f"{asset}: payout da digital indisponível agora"
        return None

    def _instrument(self, asset: str) -> dict | None:
        return self._instruments.get(asset)

    def tradable(self, asset: str, kind: str = BINARY) -> tuple[bool, str]:
        """Dá para comprar opção de 1 min deste tipo neste ativo agora?"""
        if kind == DIGITAL:
            info = self._digital_info(asset)
            reason = self._digital_closed_reason(asset, info, self.server_time(), self._digital_payout(info))
            return (False, reason) if reason else (True, "ok")
        info = self._instrument(asset)
        if info is None:
            return False, f"{asset} não está na lista de binárias da IQ (pares normais terminam em -op, ex.: EURUSD-op)"
        if info["kind"] != "turbo":
            return False, f"{asset} não tem binária de 1 minuto"
        reason = self._closed_reason(asset, info, self.server_time())
        return (False, reason) if reason else (True, "ok")

    @staticmethod
    def _closed_reason(asset: str, info: dict, now: float) -> str | None:
        if not info["enabled"] or info["suspended"] or not any(s[0] <= now <= s[1] for s in info["schedule"]):
            return f"{asset} está fechado para binária agora"
        return None

    def payout_now(self, asset: str, kind: str = BINARY) -> float | None:
        """Da lista de instrumentos em memória (binária) ou da última mensagem de payout (digital)."""
        if kind == DIGITAL:
            return self._digital_payout(self._digital_info(asset))
        info = self._instrument(asset)
        return info["payout"] if info and info["kind"] == "turbo" else None

    def _digital_fields(self, asset: str, info: dict | None, now: float, known: bool) -> dict:
        """Os campos da digital de um par na lista da tela. `known` = a lista de digitais já chegou."""
        if info is None:
            return {"digital": False if known else None, "digital_open": False if known else None, "digital_payout": None,
                    "digital_reason": None, "digital_expiries": [], "digital_next_open": None, "digital_next_close": None}
        payout = self._digital_payout(info)
        reason = self._digital_closed_reason(asset, info, now, payout)
        next_open, next_close = _schedule_edges(info["schedule"], now)
        if info["suspended"]:
            next_open = None  # suspenso pela IQ: a grade não diz quando volta
        return {"digital": True, "digital_open": reason is None, "digital_payout": payout, "digital_reason": reason,
                "digital_expiries": list(DIGITAL_MINUTES),
                "digital_next_open": next_open if reason is not None and not _digital_open(info, now) else None,
                "digital_next_close": next_close if reason is None else None}

    def pairs(self) -> list[dict]:
        now = self.server_time()
        digital = self._digital  # uma leitura só: a lista pode ser trocada em segundo plano no meio
        digital_known = bool(digital)
        out, with_digital, categories = [], set(), {}
        for name, info in self._instruments.items():
            # Nomes que o resto do bot não aceita (com "/", ":", espaço ou minúsculas) ficam de fora.
            if info["kind"] != "turbo" or not valid_asset(name) or normalize_asset(name) != name:
                continue
            reason = self._closed_reason(name, info, now)
            next_open, next_close = _schedule_edges(info["schedule"], now)
            # A IQ desliga a binária -op no fim de semana (enabled False), mas a grade continua dizendo quando o
            # mercado normal abre (ex.: EURUSD-op domingo 23:00). Só a suspensão não tem horário de volta.
            if info["suspended"]:
                next_open = None
            twin_digital = _digital_name(name, digital)
            if twin_digital:
                with_digital.add(twin_digital)
            category = info.get("category") or "Outros"
            categories.setdefault(name.partition("-")[0], category)
            out.append({"asset": name, "label": info.get("label") or name, "category": category,
                        "payout": info["payout"], "open": reason is None, "reason": reason,
                        "min": info.get("min"), "max": info.get("max"),
                        "expiries": list(range(1, min(info.get("count") or 1, MAX_TURBO_MINUTES) + 1)),
                        "market": "otc" if is_otc(name) else "normal", "binary": True,
                        "next_open": None if reason is None else next_open, "next_close": next_close if reason is None else None,
                        **self._digital_fields(name, digital.get(twin_digital) if twin_digital else None, now, digital_known)})
        for name, info in digital.items():  # só digital: o bot opera com "Digital" ou "A de maior payout"
            if name in with_digital or not valid_asset(name) or normalize_asset(name) != name:
                continue
            out.append({"asset": name, "label": info["label"],
                        "category": categories.get(name.partition("-")[0], info.get("category") or "Outros"),
                        "payout": None, "open": False, "reason": f"{name} não tem binária: só digital",
                        "min": None, "max": None, "expiries": [], "market": "otc" if is_otc(name) else "normal",
                        "binary": False, "next_open": None, "next_close": None,
                        **self._digital_fields(name, info, now, True)})
        return out

    def disconnect(self) -> None:
        if self._api is None:
            return
        try:
            self._call("desconectar", self._api.api.close, timeout=5)
        except Exception as exc:  # noqa: BLE001 - ao trocar de login, uma conexão que não fecha não importa
            log.debug("Conexão antiga não fechou: %s", exc)
        self._api = None

    def is_connected(self) -> bool:
        """Olha ESTA conexão, sem esperar por nada: o websocket dela está de pé e o horário da IQ continua
        chegando? (O `check_connect` da biblioteca é uma bandeira global e demora a perceber uma conexão morta.)"""
        api = self._api
        if api is None:
            return False
        try:
            if not api.api.websocket_alive():
                return False
            behind = time.time() - api.get_server_timestamp()
        except Exception:  # noqa: BLE001 - conexão pela metade
            return False
        return self._skew is None or behind - self._skew <= CLOCK_FROZEN_SECONDS

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
        return self.balance_info()[0]

    def balance_info(self) -> tuple[float, float]:
        """(saldo, bônus) numa leitura só. O site da IQ mostra os dois somados; o `get_balance` da biblioteca, só o saldo."""
        from iqoptionapi import global_value  # a biblioteca guarda aqui a carteira escolhida (demo ou real)

        raw = self._call("saldo", lambda: self._api.get_balances(), timeout=10)
        entry = _balance_entry(raw, global_value.balance_id)
        if entry is None or entry.get("amount") is None:
            raise BrokerError("Não foi possível ler o saldo")
        return float(entry["amount"]), float(entry.get("bonus_amount") or 0.0)

    def server_time(self) -> float:
        return float(self._call("horário do servidor", lambda: self._api.get_server_timestamp(), timeout=5))

    # ------------------------------------------------------------------ velas

    def get_candles(self, asset: str, timeframe: int, count: int, end_ts: float | None = None) -> list[Candle]:
        with self._history_lock:
            return self._get_candles(asset, timeframe, count, end_ts)

    def _require_known(self, asset: str) -> None:
        from iqoptionapi import constants as op_code

        if asset not in op_code.ACTIVES:
            raise BrokerError(f"Ativo {asset!r} não existe na IQ Option (pares de binária terminam em -op, ex.: EURUSD-op)")

    def _request_candles(self, asset: str, timeframe: int, count: int, end: float) -> list[dict]:
        """O mesmo pedido do `get_candles` da biblioteca, sem o laço sem pausa e sem ela reconectar por conta própria."""
        from iqoptionapi import constants as op_code

        api = self._api.api
        api.candles.candles_data = None
        api.getcandles(op_code.ACTIVES[asset], timeframe, count, end)
        while api.candles.candles_data is None:
            time.sleep(0.02)
        return api.candles.candles_data

    def _get_candles(self, asset: str, timeframe: int, count: int, end_ts: float | None) -> list[Candle]:
        self._require_known(asset)
        end = end_ts if end_ts is not None else self.server_time()
        collected: dict[int, Candle] = {}
        remaining = count
        while remaining > 0:
            batch = min(remaining, MAX_CANDLES_PER_REQUEST)
            batch_end = end
            raw = self._call(f"histórico {asset}", lambda: self._request_candles(asset, timeframe, batch, batch_end))
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

    def release_stream(self, asset: str, timeframe: int) -> None:
        """O mesmo pedido de `stop_candles_stream`, sem os 5 s por par que ela dorme para conferir se o preço parou."""
        from iqoptionapi import constants as op_code

        def send() -> None:
            key = f"{asset},{timeframe}"
            if key in self._api.subscribe_candle:  # senão a biblioteca reabre o stream ao reconectar
                self._api.subscribe_candle.remove(key)
            self._api.api.candle_generated_check[asset][timeframe] = {}
            self._api.api.unsubscribe(op_code.ACTIVES[asset], timeframe)

        self._call(f"cancelar stream {asset}", send, timeout=3)

    def stream_candles(self, asset: str, timeframe: int) -> list[Candle]:
        raw = self._call(f"stream {asset}", lambda: self._api.get_realtime_candles(asset, timeframe), timeout=5)
        if not raw:
            return []
        candles = [_to_candle(item) for item in list(raw.values())]
        return sorted(candles, key=lambda c: c.ts)

    # ------------------------------------------------------------------ sentimento dos traders

    def _mood_store(self) -> _StampedMood | None:
        """O dicionário com horário desta conexão. Se a biblioteca trocou a conexão por baixo (ela recria o objeto
        a cada login), põe um novo e esquece as assinaturas: elas morreram com a conexão antiga."""
        inner = getattr(self._api, "api", None) if self._api is not None else None
        if inner is None:
            return None
        store = inner.__dict__.get("traders_mood")
        if not isinstance(store, _StampedMood):
            store = _StampedMood()
            inner.traders_mood = store  # atributo do objeto: o aviso "traders-mood-changed" passa a gravar aqui
            self._mood_subs = set()
        return store

    def subscribe_mood(self, asset: str, force: bool = False) -> bool:
        from iqoptionapi import constants as op_code

        active_id = op_code.ACTIVES.get(asset)
        if active_id is None or self._mood_store() is None:
            return False
        if asset in self._mood_subs and not force:
            return True
        api = self._api.api
        self._call(f"sentimento {asset}", lambda: api.subscribe_Traders_mood(active_id, MOOD_INSTRUMENT), timeout=10)
        self._mood_subs.add(asset)
        return True

    def traders_mood(self, asset: str) -> tuple[float, float] | None:
        from iqoptionapi import constants as op_code

        store = self._mood_store()
        active_id = op_code.ACTIVES.get(asset)
        if store is None or active_id is None:
            return None
        value, at = store.get(active_id), store.at.get(active_id)
        if value is None or at is None:
            return None
        try:
            return float(value), time.monotonic() - at
        except (TypeError, ValueError):
            return None

    # ------------------------------------------------------------------ ordens

    def buy(self, asset: str, direction: str, amount: float, minutes: int = 1, kind: str = BINARY) -> OrderTicket:
        if self._account is AccountType.REAL and not self._allow_real:
            raise BrokerError("Conta REAL bloqueada: ordem não enviada.")
        if direction not in ("call", "put"):
            raise BrokerError(f"Direção inválida: {direction!r}")
        if amount <= 0:
            raise BrokerError("Valor da entrada precisa ser maior que zero")
        if kind not in (BINARY, DIGITAL):
            raise BrokerError(f"Tipo de opção inválido: {kind!r}")
        ok_now, why = self.tradable(asset, kind)
        if not ok_now:
            raise OrderRefused(why)
        server = self.server_time()
        skew = time.time() - server
        if abs(skew) > 3 and not self._skew_warned:
            # Não afeta a ordem (o vencimento vai calculado pelo horário da IQ), mas fica registrado.
            log.warning("Relógio do computador %+.1fs fora do horário da IQ", skew)
            self._skew_warned = True
        if kind == DIGITAL:
            return self._buy_digital(asset, direction, float(amount), minutes, server)
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

    def _place_digital(self, instrument: str, active_id: int, amount: float) -> tuple[bool, Any]:
        """O pedido do `buy_digital_spot_v2` da biblioteca, com o código já pronto e sem o laço sem pausa.
        (A biblioteca calcula o vencimento pelo relógio local, que pode estar adiantado e errar a vela.)"""
        api = self._api.api
        request_id = api.place_digital_option_v2(instrument, active_id, amount)
        while api.digital_option_placed_id.get(request_id) is None:
            time.sleep(0.02)
        answer = api.digital_option_placed_id.get(request_id)
        return isinstance(answer, int), answer

    def _buy_digital(self, asset: str, direction: str, amount: float, minutes: int, server: float) -> OrderTicket:
        info = self._digital_info(asset)
        if info is None or info.get("id") is None:
            raise BrokerError(f"{asset} não tem opção digital")
        expected = digital_expiry_for(server, minutes)
        instrument = _digital_instrument(info["id"], expected, minutes, direction)
        with self._buy_lock:
            ok, answer = self._call(f"ordem digital {asset}", lambda: self._place_digital(instrument, info["id"], amount),
                                    timeout=12)
        if not ok:  # a IQ respondeu que não: nada foi comprado
            why = str((answer.get("message") if isinstance(answer, dict) else answer) or "sem resposta")
            if "instrument" in why.lower():  # recusa do par (não do saldo ou do valor): não insiste nele
                self._digital_refused[asset] = (server + DIGITAL_REFUSED_SECONDS, why)
                log.warning("%s: a IQ recusou a digital (%s); sem digital neste par por %d h", asset, why,
                            DIGITAL_REFUSED_SECONDS // 3600)
            raise OrderRefused(f"A IQ recusou a ordem digital: {why}")
        log.info("Ordem digital %s %s %s %.2f enviada (id %s, vence %s)", self._account.value, asset, direction, amount,
                 answer, expected)
        return OrderTicket(order_id=answer, asset=asset, direction=direction, amount=amount, account=self._account.value,
                           opened_at=server, expires_at=expected, kind=DIGITAL)

    def order_result(self, ticket: OrderTicket) -> OrderResult | None:
        """Lê os avisos que a IQ manda sozinha quando a opção fecha (nada aqui espera resposta)."""
        if self._api is None:
            raise BrokerError("Conexão encerrada: o resultado não chega mais por ela")
        api = self._api.api
        if ticket.kind == DIGITAL:  # aviso "position-changed", guardado pela biblioteca pelo número da ordem
            event = ((getattr(api, "order_async", None) or {}).get(ticket.order_id) or {}).get("position-changed")
            msg = event.get("msg") if isinstance(event, dict) else None
            return _digital_result(msg, ticket.amount) if isinstance(msg, dict) else None
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
        data = self._call("ativos abertos", lambda: self._api.get_all_open_time(), timeout=60)
        return {asset: bool(info.get("open")) for asset, info in data.get(option_type, {}).items()}

    def payouts(self, option_type: str = "turbo") -> dict[str, float]:
        if self._instruments:
            return {name: info["payout"] for name, info in self._instruments.items()
                    if info["kind"] == option_type and info["payout"] is not None}
        data = self._call("payouts", lambda: self._api.get_all_profit(), timeout=30)
        out: dict[str, float] = {}
        for asset, info in data.items():
            value = info.get(option_type) if isinstance(info, dict) else None
            if value is not None:
                out[asset] = float(value)
        return out
