"""Placar de validação ao vivo (critério: 200 entradas com o pior caso acima do empate)."""

from fastapi.testclient import TestClient

from app.analytics.validation import needed_winrate, summarize_validation, verdict
from app.api.factory import create_app
from app.config import Settings
from tests.fakes import FakeBroker
from tests.helpers import random_walk

BE = 1 / 1.84  # payout de 84% (pares -op): 54,3%


def test_acerto_necessario_bate_com_o_criterio_do_documento():
    assert 0.60 <= needed_winrate(200, BE) <= 0.62  # ~61% em 200
    assert 0.58 <= needed_winrate(500, BE) <= 0.60  # ~59% em 500


def test_veredito_por_amostra():
    assert verdict(10, 6, BE)["code"] == "comecando"
    v = verdict(100, 58, BE)
    assert v["code"] == "juntando" and "Faltam 100" in v["detail"]
    assert verdict(200, 130, BE)["code"] == "vantagem"
    assert verdict(200, 90, BE)["code"] == "abaixo"
    assert verdict(200, 110, BE)["code"] == "empate"
    assert verdict(500, 275, BE)["code"] == "sem_vantagem"


def sig(result, ts, payout=0.84):
    profit = payout if result == "win" else (-1.0 if result == "loss" else 0.0)
    return {"result": result, "profit": profit, "payout": payout, "entry_ts": ts}


def test_resumo_com_ritmo_e_ordens():
    day = 86400
    signals = [sig("win", 1000 + i * 600) for i in range(12)] + [sig("loss", 9000 + i * 600) for i in range(8)]
    orders = [{"strategy": "retracao_comando", "status": "win", "profit": 1.68},
              {"strategy": "retracao_comando", "status": "loss", "profit": -2.0},
              {"strategy": "ldp_v13", "status": "win", "profit": 5.0}]
    out = summarize_validation("retracao_comando", "Retração", signals, orders, 0.85, now=1000 + 2 * day)
    assert (out["n"], out["wins"], out["target"]) == (20, 12, 200)
    assert abs(out["breakeven"] - BE) < 1e-9
    assert out["verdict"]["code"] == "comecando"
    assert out["per_day"] is not None and out["eta_days"] > 0
    assert out["orders"] == {"count": 2, "by_status": {"win": 1, "loss": 1}, "profit": -0.32}


def test_sem_entradas_ainda():
    out = summarize_validation("retracao_comando", "Retração", [], [], 0.85)
    assert out["n"] == 0 and out["winrate"] is None and out["per_day"] is None
    assert abs(out["breakeven"] - 1 / 1.85) < 1e-9


def test_rota_da_validacao(tmp_path):
    candles = random_walk(520, seed=4)
    settings = Settings(_env_file=None, data_dir=tmp_path, history_candles=500)
    client = TestClient(create_app(settings=settings, broker_factory=lambda: FakeBroker(candles[:500], candles[500:])))
    data = client.get("/api/validation").json()
    assert [s["strategy"] for s in data["strategies"]] == ["retracao_comando"]
    assert data["strategies"][0]["verdict"]["code"] == "comecando"


def test_otc_nao_conta_na_validacao(tmp_path):
    candles = random_walk(520, seed=4)
    settings = Settings(_env_file=None, data_dir=tmp_path, history_candles=500)
    client = TestClient(create_app(settings=settings, broker_factory=lambda: FakeBroker(candles[:500], candles[500:])))
    db = client.app.state.db
    for asset, otc, ts in (("EURUSD-op", False, 600), ("EURUSD-OTC", True, 600), ("GBPUSD-OTC", True, 660)):
        row = db.add_signal(origin="ao_vivo", asset=asset, timeframe=60, is_otc=otc, strategy="retracao_comando", direction="call",
                            setup="x", candle_ts=ts - 60, entry_ts=ts, entry_price=1.0, exit_price=1.1, result="win", payout=0.84, profit=0.84)
        db.add_order(signal_id=row["id"], asset=asset, timeframe=60, strategy="retracao_comando", direction="call", amount=2.0,
                     status="win", profit=1.68)
    [v] = client.get("/api/validation").json()["strategies"]
    assert v["n"] == 1 and v["orders"]["count"] == 1 and v["orders"]["profit"] == 1.68


def test_validacao_mostra_quem_opera_e_sem_ninguem_operando_quem_observa(tmp_path):
    candles = random_walk(520, seed=4)
    settings = Settings(_env_file=None, data_dir=tmp_path, history_candles=500)
    client = TestClient(create_app(settings=settings, broker_factory=lambda: FakeBroker(candles[:500], candles[500:])))

    def shown(strategies):
        client.put("/api/config", json={"strategies": strategies})
        return [s["strategy"] for s in client.get("/api/validation").json()["strategies"]]

    assert shown({"retracao_comando": "operate", "ldp_apostila": "observe"}) == ["retracao_comando"]
    assert shown({"retracao_comando": "observe", "ldp_apostila": "observe"}) == ["ldp_apostila", "retracao_comando"]
    assert shown({"retracao_comando": "off"}) == []  # nada ligado: não inventa uma estratégia para mostrar
