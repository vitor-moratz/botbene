"""Troca entre conta demo e real: só com o bot parado, a real só com a palavra REAL digitada."""

from fastapi.testclient import TestClient

from app.api.factory import create_app
from app.broker.base import AccountType
from app.config import Settings
from app.service.broker_factory import chosen_account
from app.service.config_store import ConfigStore
from tests.fakes import FakeBroker
from tests.helpers import random_walk
from tests.test_api import wait_status


def make_client(tmp_path):
    candles = random_walk(520, seed=4)
    broker = FakeBroker(candles[:500], candles[500:])
    settings = Settings(_env_file=None, data_dir=tmp_path, history_candles=500)
    return TestClient(create_app(settings=settings, broker_factory=lambda: broker, start_resolver=False))


def test_real_so_com_confirmacao_e_nao_pela_tela_de_configuracao(tmp_path):
    with make_client(tmp_path) as client:
        info = client.get("/api/account").json()
        assert info["chosen"] == "PRACTICE" and info["balance"] == 10_000.0
        r = client.post("/api/account", json={"account": "REAL"})
        assert r.status_code == 400 and "REAL" in r.json()["detail"]
        assert client.get("/api/config").json()["account"] == "PRACTICE"
        assert client.post("/api/account", json={"account": "REAL", "confirm": "real"}).json()["chosen"] == "REAL"
        assert client.post("/api/account", json={"account": "PRACTICE"}).json()["chosen"] == "PRACTICE"
        # o PUT da Configuração não troca a conta (não tem como passar para a real sem confirmar)
        client.put("/api/config", json={"account": "REAL", "stake": 3})
        assert client.get("/api/config").json()["account"] == "PRACTICE"


def test_real_exige_stop_loss_e_bot_parado(tmp_path):
    with make_client(tmp_path) as client:
        client.put("/api/config", json={"stop_loss": None})
        client.post("/api/account", json={"account": "REAL", "confirm": "REAL"})
        r = client.post("/api/bot/start", json={})
        assert r.status_code == 422 and "stop loss" in r.json()["detail"]
        client.post("/api/account", json={"account": "PRACTICE"})
        client.post("/api/bot/start", json={})
        wait_status(client, "rodando")
        assert client.post("/api/account", json={"account": "REAL", "confirm": "REAL"}).status_code == 409
        client.post("/api/bot/stop")
        wait_status(client, "parado")


def test_conta_escolhida_libera_a_real_so_quando_escolhida(tmp_path):
    settings = Settings(_env_file=None, data_dir=tmp_path)
    store = ConfigStore(tmp_path / "config.json")
    assert chosen_account(settings, store) == (AccountType.PRACTICE, False)
    store.update({"account": "REAL"})
    assert chosen_account(settings, store) == (AccountType.REAL, True)
    assert chosen_account(settings, None) == (AccountType.PRACTICE, False)  # sem a tela, vale o .env
