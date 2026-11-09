import time

from fastapi.testclient import TestClient

from app.api.factory import create_app
from app.config import Settings
from app.strategies import default_strategies
from tests.fakes import FakeBroker
from tests.helpers import random_walk


def make_client(tmp_path):
    candles = random_walk(520, seed=4)
    broker = FakeBroker(candles[:500], candles[500:])
    settings = Settings(_env_file=None, data_dir=tmp_path, history_candles=500)
    return TestClient(create_app(settings=settings, broker_factory=lambda: broker))


def wait_status(client, wanted, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        s = client.get("/api/status").json()
        if s["status"] == wanted:
            return s
        time.sleep(0.1)
    raise AssertionError(f"status não chegou em {wanted}: {s}")


def test_painel_e_api_de_ponta_a_ponta(tmp_path):
    with make_client(tmp_path) as client:
        assert "BotBene" in client.get("/").text
        assert client.get("/api/status").json()["status"] == "parado"

        client.app.state.bot._strategies_factory = default_strategies  # confere também o caminho de sinal no fechamento
        client.app.state.config.update({"assets": ["EURUSD-op"]})  # um par só (o padrão de instalação nova tem 12)
        # o campo antigo `asset` (painel velho) é ignorado: valem os pares da Configuração
        r = client.post("/api/bot/start", json={"asset": "eurusd", "timeframe": 60})
        assert r.status_code == 200
        s = wait_status(client, "rodando")
        assert [a["asset"] for a in s["assets"]] == ["EURUSD-op"]
        assert client.post("/api/bot/start", json={}).status_code == 409

        chart = client.get("/api/chart?limit=300").json()
        assert chart["asset"] == "EURUSD-op" and len(chart["candles"]) == 300

        stats = client.get("/api/stats?origin=backtest").json()
        assert stats["total"]["n"] > 0
        assert [g["key"] for g in stats["by_strategy"]] == ["ldp_v13", "ldp_v13_linhas", "wiki_pro_v21"]

        assert client.get("/api/signals?limit=5").json()
        assert [s["name"] for s in client.get("/api/strategies").json()][0] == "ldp_v13"
        # várias estratégias separadas por vírgula (os números do painel contam só as principais)
        two = client.get("/api/stats?origin=backtest&strategy=ldp_v13,wiki_pro_v21").json()
        assert [g["key"] for g in two["by_strategy"]] == ["ldp_v13", "wiki_pro_v21"]
        rows = client.get("/api/signals?limit=5000&strategy=wiki_pro_v21").json()
        assert rows and {r["strategy"] for r in rows} == {"wiki_pro_v21"}
        assert client.get("/api/status").json()["ui_version"] != "0"
        assert client.get("/").headers["cache-control"] == "no-cache"

        with client.websocket_connect("/ws/live") as ws:
            assert ws.receive_json()["type"] == "status"

        client.post("/api/bot/stop")
        wait_status(client, "parado")
        # parado: o gráfico vem do banco (última sessão)
        assert client.get("/api/chart?limit=100").json()["asset"] == "EURUSD-op"


def test_ativo_invalido_e_recusado(tmp_path):
    with make_client(tmp_path) as client:
        assert client.post("/api/bot/start", json={"asset": "EUR USD;"}).status_code == 422
        assert client.post("/api/bot/start", json={"asset": "EURUSD", "timeframe": 45}).status_code == 422
