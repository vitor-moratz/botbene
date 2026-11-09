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


def test_email_novo_sem_senha_e_recusado_e_nao_muda_nada(tmp_path):
    with make_client(tmp_path) as client:
        client.put("/api/config", json={"iq_email": "vitor@b.com", "iq_password": "senha-do-vitor"})
        r = client.put("/api/config", json={"iq_email": "bene@b.com", "iq_password": ""})
        assert r.status_code == 422 and "senha" in r.json()["detail"]
        assert client.get("/api/config").json()["iq_email"] == "vitor@b.com"
        # o mesmo e-mail (o formulário sempre manda) continua aceitando senha vazia
        assert client.put("/api/config", json={"iq_email": " VITOR@b.com", "stake": 5}).status_code == 200
        assert client.put("/api/config", json={"iq_email": "bene@b.com", "iq_password": "senha-do-bene"}).status_code == 200
    saved = json.loads((tmp_path / "config.json").read_text())
    assert saved["iq_email"] == "bene@b.com" and saved["iq_password"] == "senha-do-bene"


def test_login_do_env_nao_e_email_novo(tmp_path):
    store = ConfigStore(tmp_path / "config.json", "env@b.com", "envpass")
    store.update({"iq_email": "env@b.com", "stake": 5})  # o formulário mostra e manda o e-mail do .env
    assert store.credentials() == ("env@b.com", "envpass")


def test_config_antiga_vira_os_estados_novos_sem_perder_o_login(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"iq_email": "a@b.com", "iq_password": "x", "comparison": True,
                                "order_strategies": ["retracao_comando", "ldp_v13"], "stake": 7}))
    store = ConfigStore(path)
    cfg = store.get()
    assert cfg.strategies == {"retracao_comando": "operate"}  # script não é estratégia: fica de fora
    assert cfg.operating == ["retracao_comando"] and cfg.stake == 7 and store.credentials() == ("a@b.com", "x")
    store.update({"stake": 8})  # ao salvar, o arquivo passa a ter só os campos novos
    saved = json.loads(path.read_text())
    assert saved["strategies"] == {"retracao_comando": "operate"}
    assert "comparison" not in saved and "order_strategies" not in saved


def test_config_antiga_sem_ninguem_operando_nao_liga_nada(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"order_strategies": []}))
    assert ConfigStore(path).get().running == []


def test_estados_e_scripts_pela_tela(tmp_path):
    with make_client(tmp_path) as client:
        body = client.get("/api/config").json()
        assert body["strategies"] == {"retracao_comando": "operate"}
        assert body["strategy_names"] == ["score_ldp", "retracao_comando_v2", "retracao_comando", "ldp_apostila", "retracao_lote",
                                          "reversao_forca", "reversao_indecisao", "esticao", "deeplob_iq", "bb_rci", "bb_rci_v2"]
        assert body["chart_scripts"] == {"ldp_lines": True, "ldp_arrows": True, "wiki_pro": False}
        r = client.put("/api/config", json={"strategies": {"retracao_comando": "observe", "ldp_apostila": "off"},
                                            "chart_scripts": {"ldp_arrows": False}})
        assert r.status_code == 200
        assert r.json()["strategies"] == {"retracao_comando": "observe", "ldp_apostila": "off"}
        assert r.json()["chart_scripts"] == {"ldp_lines": True, "ldp_arrows": False, "wiki_pro": False}
        assert client.put("/api/config", json={"strategies": {"ldp_v13": "operate"}}).status_code == 422  # script não é estratégia
        assert client.put("/api/config", json={"strategies": {"retracao_comando": "talvez"}}).status_code == 422
        # o esticão e o DeepLOB ainda estão em validação: observam, mas não podem operar
        assert client.put("/api/config", json={"strategies": {"esticao": "operate"}}).status_code == 422
        assert client.put("/api/config", json={"strategies": {"deeplob_iq": "operate"}}).status_code == 422
        assert client.put("/api/config", json={"strategies": {"esticao": "observe"}}).json()["strategies"] == {"esticao": "observe"}
        assert client.put("/api/config", json={"chart_scripts": {"outro": True}}).status_code == 422


def test_validacao(tmp_path):
    with make_client(tmp_path) as client:
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
        assert client.post("/api/bot/focus", json={"asset": "USD JPY;"}).status_code == 422
        assert client.get("/api/chart?asset=GBPUSD&limit=100").json()["asset"] == "GBPUSD"
        client.post("/api/bot/stop")
        wait_status(client, "parado")


def test_instalacao_nova_vem_com_os_pares_op_do_estudo_e_troca_automatica():
    from app.research.dataset import RESEARCH_ASSETS
    from app.service.config_store import DEFAULT_PAIRS, UserConfig

    cfg = UserConfig()
    assert cfg.assets == list(DEFAULT_PAIRS) and all(a.endswith("-op") for a in cfg.assets)
    assert cfg.auto_market is True
    assert set(DEFAULT_PAIRS) == set(RESEARCH_ASSETS)  # os mesmos pares da pesquisa (velas guardadas para o estudo)
