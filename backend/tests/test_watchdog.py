"""Vigia da conexão: falha solta não derruba, falhas seguidas / horário parado / preço parado reconectam."""

import time

import pytest

from app.broker.base import BrokerError, OrderResult
from app.broker.iqoption import IQOptionBroker
from app.config import Settings
from app.db.database import Database
from app.risk import RiskConfig
from app.service.bot import BotService
from app.service.events import EventHub
from app.service.orders import OrderManager
from tests.fakes import FakeBroker
from tests.helpers import random_walk


class FlakyBroker(FakeBroker):
    """Stream que falha nas próximas `fail` leituras; registra disconnect e reaberturas de stream."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fail = 0
        self.disconnected = False
        self.streams_started: list[str] = []

    def stream_candles(self, asset, timeframe):
        if self.fail:
            self.fail -= 1
            raise BrokerError("A IQ Option não respondeu a 'stream' em 5s")
        return super().stream_candles(asset, timeframe)

    def start_stream(self, asset, timeframe, buffer=10):
        self.streams_started.append(asset)

    def disconnect(self):
        self.disconnected = True


def candles(n_live=40, seed=5):
    data = random_walk(500 + n_live, seed=seed)
    return data[:500], data[500:]


def make(tmp_path, brokers, assets=("EURUSD",)):
    """Bot com uma fila de corretoras: cada conexão nova pega a próxima."""
    settings = Settings(_env_file=None, data_dir=tmp_path, history_candles=500)
    db = Database(settings.db_url())
    queue = list(brokers)
    made = []

    def factory():
        if not queue:
            raise BrokerError("sem internet")
        item = queue.pop(0)
        if isinstance(item, Exception):  # esta tentativa de conexão falha
            raise item
        made.append(item)
        return item

    bot = BotService(settings, db, EventHub(), factory)
    bot.configure(list(assets), 60)
    return bot, db, made


def wait_for(cond, timeout=8.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(0.02)
    return False


def test_uma_falha_solta_nao_reconecta(tmp_path):
    history, live = candles()
    broker = FlakyBroker(history, live)
    bot, _, _ = make(tmp_path, [broker])
    bot._bootstrap(broker)
    bot._mark_healthy()
    broker.fail = 1
    assert bot._poll_guarded(broker) is None
    assert bot._poll_failures == 1
    assert bot._poll_guarded(broker) is None
    assert bot._poll_failures == 0  # voltou a responder: conta do zero


def test_falhas_seguidas_pedem_reconexao(tmp_path):
    history, live = candles()
    broker = FlakyBroker(history, live)
    bot, _, _ = make(tmp_path, [broker])
    bot._bootstrap(broker)
    bot._mark_healthy()
    broker.fail = 3
    assert bot._poll_guarded(broker) is None
    assert bot._poll_guarded(broker) is None
    problem = bot._poll_guarded(broker)
    assert problem and "parou de responder" in problem


def test_horario_da_iq_parado_pede_reconexao(tmp_path):
    history, _ = candles()
    broker = FlakyBroker(history, [])  # sem velas novas: o horário da corretora falsa não anda
    bot, _, _ = make(tmp_path, [broker])
    bot._bootstrap(broker)
    bot._mark_healthy()
    bot.clock_stall_seconds, bot.stall_seconds = 0.01, 1000
    assert bot._poll_guarded(broker) is None  # primeira leitura: guarda o horário
    time.sleep(0.03)
    problem = bot._poll_guarded(broker)
    assert problem and "horário da IQ parou" in problem


def test_conexao_caida_pede_reconexao(tmp_path):
    history, live = candles()
    broker = FlakyBroker(history, live)
    bot, _, _ = make(tmp_path, [broker])
    bot._bootstrap(broker)
    bot._mark_healthy()
    broker.is_connected = lambda: False
    bot._next_conn_check = 0
    problem = bot._poll_guarded(broker)
    assert problem and "conexão caiu" in problem


def test_par_aberto_sem_preco_reabre_o_stream_e_depois_reconecta(tmp_path):
    history, live = candles()
    broker = FlakyBroker(history, live)
    bot, _, _ = make(tmp_path, [broker], assets=("EURUSD", "GBPUSD"))
    bot._bootstrap(broker)
    bot._mark_healthy()
    bot.stall_seconds = 100
    broker.streams_started.clear()  # os do início não contam
    a, b = bot.runners["EURUSD"], bot.runners["GBPUSD"]
    now = time.monotonic()
    a.last_data, b.last_data = now - 1000, now
    assert bot._health(broker) is None  # só um par parado: reabre o stream dele
    assert broker.streams_started == ["EURUSD"]
    a.last_data = time.monotonic() - 1000  # continuou parado depois de reabrir
    problem = bot._health(broker)
    assert problem and "nenhum preço novo" in problem


def test_par_fechado_sem_preco_nao_conta(tmp_path):
    history, live = candles()
    broker = FlakyBroker(history, live)
    bot, _, _ = make(tmp_path, [broker])
    bot._bootstrap(broker)
    bot._mark_healthy()
    bot.stall_seconds = 100
    r = bot.runners["EURUSD"]
    r.tradable = (False, "EURUSD está fechado para binária agora")
    r.last_data = time.monotonic() - 1000
    assert bot._health(broker) is None


def test_preco_repetido_nao_conta_como_vivo(tmp_path):
    history, _ = candles()
    broker = FlakyBroker(history, [])
    bot, _, _ = make(tmp_path, [broker])
    bot._bootstrap(broker)
    bot._mark_healthy()
    r = bot.runners["EURUSD"]
    same = history[-1]
    broker.stream_candles = lambda asset, tf: [same]
    bot._poll(broker)
    seen = r.last_data
    time.sleep(0.02)
    bot._poll(broker)
    assert r.last_data == seen  # mesma vela, mesmo preço: o relógio do vigia não anda


def test_reconecta_sozinho_e_volta_a_rodar(tmp_path):
    history, live = candles()
    first = FlakyBroker(history, list(live))
    second = FlakyBroker(history, list(live))
    bot, db, made = make(tmp_path, [first, second])
    bot.poll_seconds, bot.max_poll_failures, bot.reconnect_waits = 0.01, 2, (0.01,)
    bot.clock_stall_seconds = bot.stall_seconds = 1000
    first.fail = 10_000  # a primeira conexão morre logo depois de carregar
    bot.start(["EURUSD"], 60)
    try:
        assert wait_for(lambda: bot.connection["drops"] == 1 and bot.status == "rodando" and len(made) == 2)
        assert first.disconnected  # a velha fecha antes de abrir a nova
        drop = bot.connection["last_drop"]
        assert drop["attempts"] == 1 and "parou de responder" in drop["reason"]
        assert bot.connection["state"] == "ok"
        assert bot.runners["EURUSD"].ready
        reasons = [s.stop_reason for s in db_sessions(db)]
        assert any(r and r.startswith("conexão caiu") for r in reasons)
    finally:
        bot.stop()
    assert bot.status == "parado"


def test_tentativas_que_falham_continuam_ate_parar(tmp_path):
    history, live = candles()
    first = FlakyBroker(history, list(live))
    bot, _, made = make(tmp_path, [first])  # depois da primeira, toda conexão falha
    bot.poll_seconds, bot.max_poll_failures, bot.reconnect_waits = 0.01, 1, (0.01,)
    bot.clock_stall_seconds = bot.stall_seconds = 1000
    first.fail = 10_000
    bot.start(["EURUSD"], 60)
    try:
        assert wait_for(lambda: bot.status == "reconectando" and bot.connection["attempt"] >= 3)
        assert "sem internet" in (bot.connection["last_error"] or "")
        assert bot.snapshot()["connection"]["state"] == "reconectando"
    finally:
        bot.stop()
    assert wait_for(lambda: bot.status == "parado")


def test_login_que_nao_responde_tenta_de_novo(tmp_path):
    history, live = candles()
    ok = FlakyBroker(history, list(live))
    bot, _, made = make(tmp_path, [BrokerError("A IQ Option não respondeu a 'login' em 45s"), ok])
    bot.poll_seconds, bot.reconnect_waits = 0.01, (0.01,)
    bot.clock_stall_seconds = bot.stall_seconds = 1000
    bot.start(["EURUSD"], 60)
    try:
        assert wait_for(lambda: bot.status == "rodando" and made == [ok])
        assert bot.connection["drops"] == 0  # não conseguir entrar não é "queda"
        assert bot.connection["state"] == "ok" and bot.connection["last_drop"] is None
    finally:
        bot.stop()


def test_senha_errada_nao_fica_tentando(tmp_path):
    bot, _, _ = make(tmp_path, [BrokerError('Falha no login da IQ Option: {"code":"invalid_credentials"}')])
    bot.reconnect_waits = (0.01,)
    bot.start(["EURUSD"], 60)
    assert wait_for(lambda: bot.status == "erro")
    assert "invalid_credentials" in bot.error
    assert not bot.running


def test_login_recusado_nao_repete_sozinho_ate_o_usuario_agir(tmp_path, monkeypatch):
    # Sem espera entre tentativas: quem segura aqui é a recusa, não o tempo.
    monkeypatch.setattr("app.service.bot.CONNECT_BACKOFF_SECONDS", 0)
    refused = BrokerError('Falha no login da IQ Option: {"code":"invalid_credentials"}')
    history, live = candles()
    ok = FlakyBroker(history, list(live))
    bot, _, made = make(tmp_path, [refused, ok])
    with pytest.raises(BrokerError, match="invalid_credentials"):
        bot.shared_broker()
    # painel, resolvedor e arquivo de velas: nada disso gasta outra tentativa de login
    for _ in range(3):
        with pytest.raises(BrokerError, match="invalid_credentials"):
            bot.shared_broker()
        assert "invalid_credentials" in bot.account_info()["error"]
    assert made == []
    bot.invalidate_broker()  # o usuário trocou o login
    assert bot.shared_broker() is ok


def test_falha_passageira_continua_tentando(tmp_path, monkeypatch):
    monkeypatch.setattr("app.service.bot.CONNECT_BACKOFF_SECONDS", 0)
    history, live = candles()
    ok = FlakyBroker(history, list(live))
    bot, _, _ = make(tmp_path, [BrokerError("A IQ Option não respondeu a 'login' em 45s"), ok])
    with pytest.raises(BrokerError, match="não respondeu"):
        bot.shared_broker()
    assert bot.shared_broker() is ok


def test_iniciar_o_bot_tenta_o_login_de_novo(tmp_path):
    refused = BrokerError('Falha no login da IQ Option: {"code":"invalid_credentials"}')
    history, live = candles()
    ok = FlakyBroker(history, list(live))
    bot, _, made = make(tmp_path, [refused, ok])
    with pytest.raises(BrokerError):
        bot.shared_broker()
    bot.poll_seconds = 0.01
    bot.clock_stall_seconds = bot.stall_seconds = 1000
    bot.start(["EURUSD"], 60)
    try:
        assert wait_for(lambda: bot.status == "rodando" and made == [ok])
    finally:
        bot.stop()


def db_sessions(db):
    from sqlalchemy import select

    from app.db.models import SessionRow

    with db.Session() as s:
        return list(s.scalars(select(SessionRow)))


# ---------------------------------------------------------------- ordens e conexão que caiu

def test_ordem_acha_o_resultado_na_conexao_nova(tmp_path):
    settings = Settings(_env_file=None, data_dir=tmp_path)
    db = Database(settings.db_url())
    history, _ = candles()
    old, new = FakeBroker(history, []), FakeBroker(history, [])

    def dead(ticket):
        raise AttributeError("'NoneType' object has no attribute 'api'")  # conexão velha já fechada

    old.order_result = dead
    new.results[1] = OrderResult("win", 1.6)
    om = OrderManager(db, EventHub(), lambda: old, sleep=lambda s: None, now=old.server_time,
                      threaded=False, current_broker=lambda: new)
    om.reset(RiskConfig(stake=2))
    row = om.submit(asset="EURUSD", timeframe=60, strategy="retracao_comando", direction="call",
                    ref_price=1.1, signal_id=None, payout=0.8)
    got = db.list_orders()[0]
    assert row["status"] == "enviando" and got["status"] == "win" and got["profit"] == 1.6
    assert om.open_count == 0


def test_iq_sem_conexao_vira_erro_de_conexao():
    broker = IQOptionBroker("a@b.c", "x")
    with pytest.raises(BrokerError):
        broker.server_time()
    with pytest.raises(BrokerError):
        broker.order_result(None)
    broker._api = object()
    with pytest.raises(BrokerError, match="Erro da IQ Option"):
        broker._call("teste", lambda: {}["falta"])
