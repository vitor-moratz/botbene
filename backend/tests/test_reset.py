"""Zerar o histórico: guarda cópia, apaga entradas/ordens/sessões/velas e mantém a configuração."""

import sqlite3

from fastapi.testclient import TestClient

from app.api.factory import create_app
from app.config import Settings
from app.strategies import default_strategies
from tests.fakes import FakeBroker
from tests.helpers import random_walk
from tests.test_api import wait_status


def test_zera_com_copia_e_mantem_a_configuracao(tmp_path):
    candles = random_walk(520, seed=4)
    broker = FakeBroker(candles[:500], candles[500:])
    settings = Settings(_env_file=None, data_dir=tmp_path, history_candles=500)
    with TestClient(create_app(settings=settings, broker_factory=lambda: broker, start_resolver=False)) as client:
        client.put("/api/config", json={"stake": 3, "assets": ["EURUSD-op"]})
        client.app.state.bot._strategies_factory = default_strategies  # para ter sinais a apagar
        client.post("/api/bot/start", json={})
        wait_status(client, "rodando")
        assert client.post("/api/data/reset").status_code == 409  # com o bot rodando, não deixa
        client.post("/api/bot/stop")
        wait_status(client, "parado")
        before = client.get("/api/signals?limit=5000").json()
        assert before

        r = client.post("/api/data/reset")
        assert r.status_code == 200
        body = r.json()
        assert body["apagado"]["signals"] == len(before) and body["apagado"]["candles"] > 0

        assert client.get("/api/signals?limit=5000").json() == []
        assert client.get("/api/stats?origin=backtest").json()["total"]["n"] == 0
        assert client.get("/api/chart?limit=100").json()["candles"] == []
        assert client.get("/api/config").json()["stake"] == 3  # configuração continua
        # a cópia tem o que existia antes
        copy = sqlite3.connect(body["copia"])
        assert copy.execute("select count(*) from signals").fetchone()[0] == len(before)
        copy.close()
        # e o bot volta a rodar normalmente depois
        client.post("/api/bot/start", json={})
        wait_status(client, "rodando")
        client.post("/api/bot/stop")
        wait_status(client, "parado")
