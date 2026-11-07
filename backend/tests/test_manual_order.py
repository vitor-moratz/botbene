"""Entrada manual: a decisão é do usuário, então os stops do bot não bloqueiam e o placar dele não muda."""

import pytest
from fastapi.testclient import TestClient

from app.api.factory import create_app
from app.broker.base import OrderResult
from app.config import Settings
from app.db.database import Database
from app.paper import LOSS
from app.risk import RiskConfig
from app.service.chart import order_entries
from app.service.events import EventHub
from app.service.orders import DuplicateOrderError, OrderManager
from app.strategies import MANUAL
from tests.fakes import FakeBroker
from tests.test_watchdog import candles, wait_for


def pair(asset="EURUSD-OTC", **extra):
    return {"asset": asset, "label": asset, "category": "Moedas", "payout": 0.88, "open": True, "reason": None,
            "min": 2, "max": 20000, "expiries": [1, 2, 3, 4, 5]} | extra


def manager(tmp_path, broker, **cfg):
    db = Database(Settings(_env_file=None, data_dir=tmp_path).db_url())
    om = OrderManager(db, EventHub(), lambda: broker, sleep=lambda s: None, now=broker.server_time, threaded=False)
    om.reset(RiskConfig(stake=2, **cfg))
    return om, db


def send(om, direction="call", amount=5.0, minutes=3, asset="EURUSD-OTC"):
    return om.submit_manual(asset=asset, timeframe=60, direction=direction, amount=amount, minutes=minutes, ref_price=1.1,
                            requested_at=1000, account="PRACTICE")


def test_envia_com_o_valor_e_a_expiracao_escolhidos(tmp_path):
    broker = FakeBroker(candles()[0], [])
    om, db = manager(tmp_path, broker)
    send(om, amount=7.5, minutes=4)
    [row] = db.list_orders()
    assert broker.buy_minutes == [4]
    assert broker.tickets[0].amount == 7.5
    assert row["strategy"] == MANUAL and row["amount"] == 7.5 and row["status"] == "win" and row["requested_at"] == 1000


def test_stops_atingidos_nao_bloqueiam(tmp_path):
    broker = FakeBroker(candles()[0], [])
    om, db = manager(tmp_path, broker, stop_loss=2, stop_win=2, max_trades=1, max_consecutive_losses=1)
    om.risk.closed(LOSS, -2.0, 2.0)
    om.risk.closed(LOSS, -2.0, 2.0)
    assert om.risk.check(0.8)[0] is False
    send(om)
    assert db.list_orders()[0]["status"] == "win"


def test_placar_e_martingale_do_bot_nao_mudam(tmp_path):
    broker = FakeBroker(candles()[0], [])
    broker.results[1] = OrderResult(LOSS, -5.0)
    om, _ = manager(tmp_path, broker, martingale=True)
    send(om)
    risk = om.snapshot(0.8)
    assert (risk["pnl"], risk["trades"], risk["losses"], risk["consecutive_losses"], risk["gale_level"]) == (0.0, 0, 0, 0, 0)
    assert risk["open_orders"] == 0 and risk["manual_open"] == 0 and om.open_count == 0


def test_ordem_recusada_pela_iq_vira_erro_e_nao_fica_aberta(tmp_path):
    broker = FakeBroker(candles()[0], [])
    broker.refuse_orders = "A IQ recusou a ordem: valor abaixo do mínimo"
    om, db = manager(tmp_path, broker)
    send(om)
    [row] = db.list_orders()
    assert row["status"] == "erro" and "mínimo" in row["error"]
    assert om.open_count == 0


def test_servidor_espera_a_manual_aberta_antes_de_reiniciar(tmp_path):
    broker = FakeBroker(candles()[0], [])
    db = Database(Settings(_env_file=None, data_dir=tmp_path).db_url())
    om = OrderManager(db, EventHub(), lambda: broker, threaded=True, sleep=lambda s: None, now=broker.server_time)
    om._start = lambda row, minutes=1: None  # fica "aberta": o resultado ainda não veio
    send(om)
    assert om.open_count == 1 and om.snapshot()["manual_open"] == 1 and om.snapshot()["open_orders"] == 0


def test_placar_refeito_depois_de_reiniciar_nao_conta_a_manual():
    om = OrderManager.__new__(OrderManager)
    import threading

    from app.risk import RiskManager

    om._lock, om.risk = threading.Lock(), RiskManager(RiskConfig(stake=2))
    om.restore([{"id": 1, "requested_at": 1, "strategy": MANUAL, "status": "loss", "profit": -50.0, "amount": 50.0},
                {"id": 2, "requested_at": 2, "strategy": "retracao_comando", "status": "win", "profit": 1.6, "amount": 2.0}])
    assert om.risk.pnl == 1.6 and om.risk.trades == 1 and om.risk.losses == 0


def test_clique_duplo_nao_manda_duas(tmp_path):
    broker = FakeBroker(candles()[0], [])
    om, db = manager(tmp_path, broker)
    send(om)
    with pytest.raises(DuplicateOrderError):
        send(om)
    assert len(db.list_orders()) == 1
    send(om, direction="put")  # a outra direção é outra entrada
    send(om, asset="GBPUSD-OTC")  # outro par também
    assert len(db.list_orders()) == 3


def test_marca_fica_na_vela_em_que_entrou_mesmo_vencendo_depois():
    order = {"id": 1, "status": "aberta", "signal_id": None, "strategy": MANUAL, "direction": "call", "ref_price": 1.1, "amount": 2.0,
             "requested_at": 6010, "expires_at": 6300, "profit": None, "account": "PRACTICE"}
    [entry] = order_entries([order], [], 60, 0)
    assert entry["time"] == 6000 and entry["strategy"] == MANUAL


# ---------------------------------------------------------------- pela API

@pytest.fixture
def client(tmp_path):
    broker = FakeBroker(candles()[0], [])
    broker.pair_list = [pair(), pair("FECHADO-OTC", open=False, reason="FECHADO-OTC está fechado para binária agora"), pair("UM-OTC", expiries=[1])]
    settings = Settings(_env_file=None, data_dir=tmp_path, history_candles=500)
    with TestClient(create_app(settings=settings, broker_factory=lambda: broker, start_resolver=False)) as c:
        c.broker = broker
        yield c
        c.app.state.bot.watcher.stop()


def post(client, **body):
    return client.post("/api/orders/manual", json={"asset": "EURUSD-OTC", "direction": "call", "amount": 2, "minutes": 1} | body)


def test_api_envia_com_o_bot_parado(client):
    r = post(client, minutes=5, amount=3.456)
    assert r.status_code == 200 and r.json()["strategy"] == MANUAL
    assert wait_for(lambda: client.broker.buy_minutes == [5])
    assert client.broker.tickets[0].amount == 3.46
    assert client.get("/api/status").json()["status"] == "parado"
    assert wait_for(lambda: client.get("/api/orders").json()[0]["status"] == "win")


def test_api_recusa_o_que_a_iq_nao_aceita(client):
    closed = post(client, asset="FECHADO-OTC")
    assert closed.status_code == 422 and "fechado" in closed.json()["detail"]
    assert post(client, asset="UM-OTC", minutes=3).status_code == 422
    assert post(client, amount=1).status_code == 422  # abaixo do mínimo da IQ
    assert post(client, amount=20001).status_code == 422
    assert post(client, asset="NAOEXISTE-OTC").status_code == 422
    assert post(client, direction="sobe").status_code == 422
    assert post(client, minutes=15).status_code == 422
    assert post(client, amount=0).status_code == 422
    assert client.broker.tickets == []


def test_api_clique_duplo_e_conflito(client):
    assert post(client).status_code == 200
    assert post(client).status_code == 409
    assert wait_for(lambda: len(client.broker.tickets) == 1)


def test_api_recusa_durante_a_reconexao(client):
    client.app.state.bot.status = "reconectando"
    r = post(client)
    client.app.state.bot.status = "parado"
    assert r.status_code == 409 and "reconectando" in r.json()["detail"]


def test_api_entrada_manual_nao_entra_nas_estatisticas(client):
    assert post(client).status_code == 200
    assert wait_for(lambda: client.get("/api/orders").json()[0]["status"] == "win")
    stats = client.get("/api/stats?period=hoje&origin=ao_vivo").json()
    assert stats["total"]["n"] == 0 and stats["by_strategy"] == []
    assert client.get("/api/signals?period=hoje").json() == []


def test_api_lista_os_pares_e_os_do_bot(client):
    data = client.get("/api/pairs").json()
    assert data["error"] is None
    assert [p["asset"] for p in data["pairs"]] == ["EURUSD-OTC", "FECHADO-OTC", "UM-OTC"]
    assert data["bot_assets"] == client.app.state.config.get().assets


def test_api_lista_vazia_sem_conexao(tmp_path):
    from app.broker.base import BrokerError

    def no_login():
        raise BrokerError("sem internet")

    settings = Settings(_env_file=None, data_dir=tmp_path)
    with TestClient(create_app(settings=settings, broker_factory=no_login, start_resolver=False)) as c:
        data = c.get("/api/pairs").json()
        assert data["pairs"] == [] and "sem internet" in data["error"] and data["bot_assets"]
        r = c.post("/api/orders/manual", json={"asset": "EURUSD-OTC", "direction": "call", "amount": 2, "minutes": 1})
        assert r.status_code == 503 and "sem internet" in r.json()["detail"]


def test_api_escolher_par_fora_da_lista_abre_o_grafico(client):
    s = client.post("/api/bot/focus", json={"asset": "eurjpy-otc"}).json()
    assert s["asset"] == "EURJPY-OTC" and s["status"] == "parado" and s["watch"]["asset"] == "EURJPY-OTC"
    assert wait_for(lambda: client.get("/api/chart?limit=100").json()["candles"])
    assert client.get("/api/chart?limit=100").json()["asset"] == "EURJPY-OTC"
