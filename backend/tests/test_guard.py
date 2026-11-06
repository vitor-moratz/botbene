"""Último recurso do vigia: reinício do servidor, retomada da sessão e conexão compartilhada."""

import json
import os
import time

import pytest
from fastapi.testclient import TestClient

from app.api.factory import create_app
from app.broker.base import BrokerError
from app.config import Settings
from app.db.database import Database
from app.risk import RiskConfig
from app.service.bot import BotService
from app.service.events import EventHub
from app.service.guard import MIN_RESTART_GAP, ORDER_WAIT_SECONDS, RESTART_CODE, RESUME_MAX_AGE, ProcessGuard
from app.service.orders import OrderManager
from tests.fakes import FakeBroker
from tests.helpers import random_walk


def make_bot(tmp_path, factory=None):
    settings = Settings(_env_file=None, data_dir=tmp_path, history_candles=500)
    db = Database(settings.db_url())
    candles = random_walk(520, seed=3)
    broker = FakeBroker(candles[:500], candles[500:])
    bot = BotService(settings, db, EventHub(), factory or (lambda: broker))
    return bot, db, broker


def make_guard(tmp_path, stuck=0):
    bot, db, _ = make_bot(tmp_path)
    exits = []
    guard = ProcessGuard(bot, tmp_path, stuck=lambda: stuck, exit_fn=exits.append)
    return guard, bot, db, exits


def order(db, status, amount=2.0, profit=None, requested_at=None):
    return db.add_order(asset="EURUSD-op", timeframe=60, strategy="retracao_comando", direction="call", ref_price=1.1,
                        signal_id=None, amount=amount, gale=0, status=status, profit=profit,
                        requested_at=requested_at or int(time.time()))


# ---------------------------------------------------------------- quando reinicia

def test_tudo_bem_nao_reinicia(tmp_path):
    guard, _, _, exits = make_guard(tmp_path, stuck=2)
    guard.check()
    assert not exits and not guard.resume_path.exists()


def test_chamadas_presas_reiniciam(tmp_path):
    guard, _, _, exits = make_guard(tmp_path, stuck=6)
    guard.check()
    assert exits == [RESTART_CODE]
    info = json.loads(guard.resume_path.read_text(encoding="utf-8"))
    assert "6 chamadas" in info["why"] and info["resume"] is False  # bot parado: só reinicia o servidor


def test_login_que_nunca_responde_reinicia(tmp_path):
    guard, bot, _, exits = make_guard(tmp_path)
    bot.hung_attempts = 3
    guard.check()
    assert not exits
    bot.hung_attempts = 4
    guard.check()
    assert exits == [RESTART_CODE]


def test_espera_a_ordem_aberta_antes_de_reiniciar(tmp_path):
    guard, bot, _, exits = make_guard(tmp_path, stuck=6)
    bot.orders.risk.opened(2.0)
    guard.check()
    assert not exits  # o resultado ainda pode chegar
    guard._waiting_since = time.time() - ORDER_WAIT_SECONDS - 1
    guard.check()
    assert exits == [RESTART_CODE]  # não espera para sempre


def test_nao_reinicia_em_sequencia(tmp_path):
    guard, _, _, exits = make_guard(tmp_path, stuck=6)
    guard.stamp_path.touch()
    guard.check()
    assert not exits  # ex.: a própria IQ fora do ar: reiniciar de novo não ajuda
    old = time.time() - MIN_RESTART_GAP - 1
    os.utime(guard.stamp_path, (old, old))
    guard.check()
    assert exits == [RESTART_CODE]


def test_aviso_de_retomada_vale_uma_vez(tmp_path):
    guard, _, _, _ = make_guard(tmp_path)
    assert guard.take_resume() is None
    guard.resume_path.write_text(json.dumps({"at": time.time(), "resume": True, "why": "x"}), encoding="utf-8")
    assert guard.take_resume()["why"] == "x"
    assert guard.take_resume() is None and not guard.resume_path.exists()
    guard.resume_path.write_text(json.dumps({"at": time.time() - RESUME_MAX_AGE - 1, "resume": True}), encoding="utf-8")
    assert guard.take_resume() is None  # velho demais
    guard.resume_path.write_text("não é json", encoding="utf-8")
    assert guard.take_resume() is None


# ---------------------------------------------------------------- retomada da sessão

def test_placar_refeito_a_partir_das_ordens(tmp_path):
    settings = Settings(_env_file=None, data_dir=tmp_path)
    db = Database(settings.db_url())
    om = OrderManager(db, EventHub(), lambda: None)
    om.reset(RiskConfig(stake=2, stop_win=None, stop_loss=5, max_trades=None))
    order(db, "win", profit=1.68, requested_at=100)
    order(db, "loss", profit=-2.0, requested_at=200)
    order(db, "sem_resultado", requested_at=300)
    order(db, "bloqueada", requested_at=400)  # nunca abriu
    om.restore(db.list_orders())
    snap = om.snapshot()
    assert (snap["trades"], snap["wins"], snap["losses"], snap["consecutive_losses"]) == (3, 1, 2, 2)
    assert snap["pnl"] == -2.32  # sem_resultado conta como perda
    assert snap["can_trade"] is True
    order(db, "loss", profit=-2.0, requested_at=500)
    om.reset(RiskConfig(stake=2, stop_win=None, stop_loss=5, max_trades=None))
    om.restore(db.list_orders())
    assert om.snapshot()["can_trade"] is False  # o stop loss continua valendo depois de reiniciar


def test_retoma_o_bot_com_o_placar_na_demo(tmp_path):
    bot, db, _ = make_bot(tmp_path)
    started = int(time.time()) - 600
    order(db, "win", profit=1.68, requested_at=started + 10)
    order(db, "loss", profit=-2.0, requested_at=started - 10)  # de antes da sessão: não conta
    bot.config.update({"stake": 2})
    info = {"at": time.time() - 5, "why": "6 chamadas à IQ presas", "resume": True, "assets": ["EURUSD"],
            "timeframe": 60, "started_at": started, "drops": 2}
    bot.resume(info)
    try:
        assert bot.running
        assert bot.started_at == started and bot.connection["drops"] == 3
        assert "servidor reiniciado" in bot.connection["last_drop"]["reason"]
        snap = bot.orders.snapshot()
        assert (snap["trades"], snap["pnl"]) == (1, 1.68)
    finally:
        bot.stop()


def test_na_conta_real_nao_volta_sozinho(tmp_path):
    bot, _, _ = make_bot(tmp_path)
    bot.config.update({"account": "REAL", "stop_loss": 10})
    bot.resume({"at": time.time(), "why": "travou", "resume": True, "assets": ["EURUSD"], "timeframe": 60})
    assert not bot.running and bot.status == "erro"
    assert "conta real" in bot.error


def test_servidor_supervisionado_retoma_e_fecha_ordens_orfas(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTBENE_SUPERVISED", "1")
    candles = random_walk(520, seed=4)
    settings = Settings(_env_file=None, data_dir=tmp_path, history_candles=500)
    db = Database(settings.db_url())
    orphan = order(db, "aberta")
    (tmp_path / "retomar.json").write_text(json.dumps(
        {"at": time.time(), "why": "teste", "resume": True, "assets": ["EURUSD"], "timeframe": 60, "started_at": int(time.time()) - 60}),
        encoding="utf-8")
    app = create_app(settings=settings, db=db, broker_factory=lambda: FakeBroker(candles[:500], candles[500:]), start_resolver=False)
    with TestClient(app) as client:
        s = client.get("/api/status").json()
        assert s["status"] in ("conectando", "rodando") and s["connection"]["drops"] == 1
        assert not (tmp_path / "retomar.json").exists()
        got = db.list_orders()[0]
        assert got["id"] == orphan["id"] and got["status"] == "sem_resultado" and "reiniciou" in got["error"]


# ---------------------------------------------------------------- conexão compartilhada

def test_login_que_falhou_nao_e_tentado_de_novo_pelo_painel(tmp_path):
    calls = []

    def factory():
        calls.append(1)
        raise BrokerError("A IQ Option não respondeu a 'login' em 45s")

    bot, _, _ = make_bot(tmp_path, factory)
    with pytest.raises(BrokerError):
        bot.shared_broker()
    with pytest.raises(BrokerError, match="login"):
        bot.shared_broker()
    assert len(calls) == 1  # o segundo pedido recebeu o mesmo erro, sem abrir outro login
    assert bot.account_info()["error"] and len(calls) == 1
    with pytest.raises(BrokerError):
        bot.shared_broker(force=True)
    assert len(calls) == 2  # o bot e o botão Testar conexão sempre tentam


def test_senha_recusada_nao_e_tentada_de_novo_sem_ninguem_agir(tmp_path, monkeypatch):
    calls = []

    def factory():
        calls.append(1)
        raise BrokerError("A IQ recusou o e-mail ou a senha (invalid_credentials)")

    bot, _, _ = make_bot(tmp_path, factory)
    with pytest.raises(BrokerError):
        bot.shared_broker()
    later = time.monotonic() + 86400  # um dia depois: o painel e o arquivo de velas continuam chamando
    monkeypatch.setattr("app.service.bot.time.monotonic", lambda: later)
    with pytest.raises(BrokerError, match="recusou"):
        bot.shared_broker()
    assert len(calls) == 1  # repetir senha errada sozinho pode bloquear a conta
    with pytest.raises(BrokerError):
        bot.shared_broker(force=True)  # o usuário clicou em Testar conexão ou Iniciar bot
    assert len(calls) == 2
    bot.invalidate_broker()  # trocou o login
    with pytest.raises(BrokerError):
        bot.shared_broker()
    assert len(calls) == 3


def test_troca_de_conexao_morta_fecha_a_velha(tmp_path):
    candles = random_walk(10, seed=1)
    closed = []

    class Dead(FakeBroker):
        def is_connected(self):
            return False

        def disconnect(self):
            closed.append(self)

    first, second = Dead(candles, []), FakeBroker(candles, [])
    queue = [first, second]
    bot, _, _ = make_bot(tmp_path, lambda: queue.pop(0))
    assert bot.shared_broker() is first
    assert bot.shared_broker() is second
    assert closed == [first]


def test_painel_nao_abre_conexao_durante_a_reconexao(tmp_path):
    calls = []
    bot, _, _ = make_bot(tmp_path, lambda: calls.append(1))
    bot.status = "reconectando"
    assert bot.account_info()["error"] == "reconectando à IQ Option"
    assert not calls
