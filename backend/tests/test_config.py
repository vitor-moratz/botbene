"""Configuração pela tela: login salvo sem voltar para o painel, validação e rotas novas."""

import json
import os
import stat

from fastapi.testclient import TestClient

from app.api.factory import create_app
from app.config import Settings
from app.service.config_store import ConfigStore
from tests.fakes import FakeBroker
from tests.helpers import random_walk
from tests.test_api import wait_status


def make_client(tmp_path, env_email="", env_password=""):
    candles = random_walk(520, seed=4)
    broker = FakeBroker(candles[:500], candles[500:])
    settings = Settings(_env_file=None, data_dir=tmp_path, history_candles=500, iq_email=env_email, iq_password=env_password)
    return TestClient(create_app(settings=settings, broker_factory=lambda: broker, start_resolver=False))


def test_senha_fica_no_arquivo_e_nao_volta_para_o_painel(tmp_path):
    with make_client(tmp_path) as client:
        assert client.get("/api/config").json()["has_password"] is False
        r = client.put("/api/config", json={"iq_email": "a@b.com", "iq_password": "segredo123", "mode": "aprovacao", "stake": 3})
        assert r.status_code == 200
        body = r.json()
        assert "iq_password" not in body and "segredo123" not in json.dumps(body)
        assert body["has_password"] and body["credentials_source"] == "tela" and body["mode"] == "aprovacao"
        # campo de senha vazio = mantém a salva
        client.put("/api/config", json={"iq_password": "", "stake": 4})
    path = tmp_path / "config.json"
    saved = json.loads(path.read_text())
    assert saved["iq_password"] == "segredo123" and saved["stake"] == 4
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_sem_login_na_tela_vale_o_env(tmp_path):
    store = ConfigStore(tmp_path / "config.json", "env@b.com", "envpass")
    assert store.credentials() == ("env@b.com", "envpass")
    assert store.public()["credentials_source"] == "arquivo .env"
    store.update({"iq_email": "tela@b.com", "iq_password": "x"})
    assert store.credentials() == ("tela@b.com", "x")


def test_validacao(tmp_path):
    with make_client(tmp_path) as client:
        assert client.put("/api/config", json={"order_strategies": ["ldp_v13"]}).status_code == 422
        assert client.put("/api/config", json={"assets": ["EUR USD;"]}).status_code == 422
        assert client.put("/api/config", json={"stake": 0.5}).status_code == 422
        r = client.put("/api/config", json={"assets": ["eurusd-OP", "gbpusd-op", "EURUSD-op", "eurusd-otc"]})
        assert r.json()["assets"] == ["EURUSD-op", "GBPUSD-op", "EURUSD-OTC"]  # sufixo -op fica minúsculo, como na IQ


def test_testar_conexao_e_rotas_novas(tmp_path):
    with make_client(tmp_path) as client:
        assert client.post("/api/config/test").json() == {"account": "PRACTICE", "balance": 10_000.0, "currency": "USD"}
        assert client.get("/api/orders").json() == []
        assert client.post("/api/approvals/999/aprovar").status_code == 404
        client.put("/api/config", json={"assets": ["EURUSD", "GBPUSD"]})
        assert client.post("/api/bot/start", json={}).status_code == 200  # usa os ativos da Configuração
        s = wait_status(client, "rodando")
        assert [a["asset"] for a in s["assets"]] == ["EURUSD", "GBPUSD"]
        assert client.post("/api/bot/focus", json={"asset": "gbpusd"}).json()["asset"] == "GBPUSD"
        assert client.post("/api/bot/focus", json={"asset": "USDJPY"}).status_code == 404
        assert client.get("/api/chart?asset=GBPUSD&limit=100").json()["asset"] == "GBPUSD"
        client.post("/api/bot/stop")
        wait_status(client, "parado")
