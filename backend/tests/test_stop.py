"""Parar o bot: responde na hora, não espera a IQ par a par e deixa iniciar de novo na mesma conexão."""

import threading
import time
from collections import defaultdict
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.factory import create_app
from app.broker.base import BrokerError
from app.broker.iqoption import IQOptionBroker
from app.config import Settings
from app.service.bot import BotBusyError
from tests.test_watchdog import FlakyBroker, candles, db_sessions, make, wait_for

ASSETS = ["EURUSD", "GBPUSD", "USDJPY"]


class StreamBroker(FlakyBroker):
    """`stop_stream` dorme como a biblioteca da IQ; `release_stream` registra e pode segurar ou falhar."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.released: list[str] = []
        self.on_release = lambda asset: None

    def stop_stream(self, asset, timeframe):
        time.sleep(5)

    def release_stream(self, asset, timeframe):
        self.released.append(asset)
        self.on_release(asset)


def started(tmp_path, broker):
    bot, db, made = make(tmp_path, [broker], assets=ASSETS)
    bot.poll_seconds = 0.01
    bot.clock_stall_seconds = bot.stall_seconds = 1000
    bot.start(ASSETS, 60)
    assert wait_for(lambda: bot.status == "rodando")
    return bot, db, made


def test_parar_nao_espera_a_iq_par_a_par(tmp_path):
    broker = StreamBroker(*candles())
    bot, db, _ = started(tmp_path, broker)
    began = time.monotonic()
    bot.stop()
    assert time.monotonic() - began < 2
    assert bot.status == "parado" and not bot.running
    assert broker.released == ASSETS
    assert {s.stop_reason for s in db_sessions(db)} == {"parado pelo usuário"}


def test_enquanto_para_o_painel_ve_parando_e_nada_fica_aberto(tmp_path):
    broker = StreamBroker(candles()[0], [])
    gate, reached = threading.Event(), threading.Event()
    seen = {}

    def hold(asset):
        seen["sessions"] = {s.stop_reason for s in db_sessions(db)}
        seen["approval"] = bot.approvals[0]["status"]
        reached.set()
        gate.wait(5)

    broker.on_release = hold
    bot, db, _ = started(tmp_path, broker)
    bot.approvals.append({"id": 1, "status": "aguardando", "deadline": float("inf")})
    bot.stop(wait=0)
    assert bot.snapshot()["status"] == "parando"
    assert reached.wait(5)
    with pytest.raises(BotBusyError, match="parando"):
        bot.start(ASSETS, 60)
    assert seen == {"sessions": {"parado pelo usuário"}, "approval": "cancelado: bot parado"}
    gate.set()
    assert wait_for(lambda: bot.status == "parado" and not bot.running)


def test_parar_durante_a_carga_nao_carrega_o_resto_nem_volta_a_rodando(tmp_path):
    broker = StreamBroker(*candles())
    gate, reached = threading.Event(), threading.Event()
    real_get = broker.get_candles

    def slow_get(*args, **kwargs):
        reached.set()
        gate.wait(5)
        return real_get(*args, **kwargs)

    broker.get_candles = slow_get
    bot, _, _ = make(tmp_path, [broker], assets=ASSETS)
    statuses = []
    publish = bot.hub.publish

    def spy(event):
        if event["type"] == "status":
            statuses.append(event["status"])
        publish(event)

    bot.hub.publish = spy
    bot.start(ASSETS, 60)
    assert reached.wait(5)
    bot.stop(wait=0)
    assert bot.status == "parando"
    gate.set()
    assert wait_for(lambda: bot.status == "parado" and not bot.running)
    assert broker.get_candles_calls == 1  # só a história do par que já estava carregando
    assert broker.streams_started == []
    assert "rodando" not in statuses and statuses[-1] == "parado"


def test_conexao_travada_nao_segura_a_parada(tmp_path, monkeypatch):
    monkeypatch.setattr("app.service.bot.STOP_STREAMS_SECONDS", 0.05)
    broker = StreamBroker(*candles())

    def stuck(asset):
        time.sleep(0.1)
        raise BrokerError("A IQ Option não respondeu")

    broker.on_release = stuck
    bot, _, _ = started(tmp_path, broker)
    bot.stop()
    assert bot.status == "parado" and not bot.running
    assert broker.released == ASSETS[:1]  # passou do prazo: não tenta os outros


def test_parar_e_iniciar_de_novo_reabre_os_streams_na_mesma_conexao(tmp_path):
    broker = StreamBroker(*candles())
    bot, _, made = started(tmp_path, broker)
    bot.stop()
    bot.start(ASSETS, 60)
    try:
        assert wait_for(lambda: bot.status == "rodando")
        assert broker.streams_started == ASSETS * 2
        assert made == [broker]  # não fez outro login
    finally:
        bot.stop()
    assert broker.released == ASSETS * 2


def test_botao_responde_mesmo_se_o_bot_ainda_nao_terminou(tmp_path, monkeypatch):
    monkeypatch.setattr("app.api.routes.STOP_WAIT_SECONDS", 0.05)
    history, live = candles()
    broker = StreamBroker(history, live)
    gate = threading.Event()
    broker.on_release = lambda asset: gate.wait(5)
    settings = Settings(_env_file=None, data_dir=tmp_path, history_candles=500)
    with TestClient(create_app(settings=settings, broker_factory=lambda: broker)) as client:
        assert client.post("/api/bot/start", json={}).status_code == 200
        assert wait_for(lambda: client.get("/api/status").json()["status"] == "rodando")
        assert client.post("/api/bot/stop").json()["status"] == "parando"
        assert client.post("/api/bot/start", json={}).status_code == 409
        gate.set()
        assert wait_for(lambda: client.get("/api/status").json()["status"] == "parado")


def test_iq_cancela_o_stream_sem_a_pausa_da_biblioteca():
    from iqoptionapi import constants as op_code

    sent = []
    check = defaultdict(dict, {"EURUSD": {60: True}})
    broker = IQOptionBroker("a@b.c", "x")
    broker._api = SimpleNamespace(
        subscribe_candle=["EURUSD,60", "GBPUSD,60"],
        api=SimpleNamespace(candle_generated_check=check, unsubscribe=lambda active, size: sent.append((active, size))),
        # A chamada da biblioteca dorme 5 s por par: não pode ser ela.
        stop_candles_stream=lambda *a: pytest.fail("usou a chamada que espera"),
    )
    broker.release_stream("EURUSD", 60)
    assert sent == [(op_code.ACTIVES["EURUSD"], 60)]
    assert broker._api.subscribe_candle == ["GBPUSD,60"]  # não volta sozinho ao reconectar
    assert check["EURUSD"][60] == {}
