"""Tela Desempenho: só ordens enviadas à corretora, em dinheiro, separando conta real e demo."""

import time

import pytest

from app.analytics.orders import order_rows, status_counts
from app.analytics.timeline import period_start
from tests.test_config import make_client

NOW = int(time.time())
T = max(NOW - 600, period_start("hoje") + 1)  # sempre dentro de hoje, mesmo logo depois da meia-noite


def signal(db, payout=0.8, setup="gatilho 50%", strategy="retracao_comando", asset="EURUSD-op", result="win", ts=T):
    return db.add_signal(origin="ao_vivo", asset=asset, timeframe=60, is_otc=asset.endswith("-OTC"), strategy=strategy,
                         direction="call", setup=setup, candle_ts=ts - 60, entry_ts=ts, result=result, payout=payout,
                         profit=payout if result == "win" else -1.0)


def order(db, status, amount=10.0, profit=None, account="REAL", strategy="retracao_comando", asset="EURUSD-op", signal_id=None,
          ts=T):
    return db.add_order(asset=asset, timeframe=60, strategy=strategy, direction="call", amount=amount, account=account,
                        status=status, requested_at=ts, profit=profit, signal_id=signal_id)


@pytest.fixture
def client(tmp_path):
    with make_client(tmp_path) as c:
        db = c.app.state.db
        s1 = signal(db, payout=0.8)
        s2 = signal(db, payout=0.9, setup="outro setup", ts=T + 60)
        order(db, "win", amount=10, profit=8.5, signal_id=s1["id"])          # pagou 85%
        order(db, "loss", amount=10, profit=-10, signal_id=s2["id"], ts=T + 60)
        order(db, "empate", amount=5, profit=0.0, strategy="manual", asset="GBPUSD-OTC", ts=T + 120)
        order(db, "aberta", amount=10)
        order(db, "erro", amount=10)
        order(db, "bloqueada", amount=10)
        order(db, "sem_resultado", amount=10)
        order(db, "win", amount=100, profit=90, account="PRACTICE")          # demo: não soma com a real
        signal(db, payout=0.8, result="loss", ts=T + 180)                   # entrada só avaliada: não é ordem
        c.db = db
        yield c


def get(client, **params):
    r = client.get("/api/stats/orders", params={"period": "hoje", **params})
    assert r.status_code == 200, r.text
    return r.json()


def test_conta_so_ordens_com_resultado_em_dinheiro(client):
    st = get(client, account="REAL")
    t = st["total"]
    assert (t["wins"], t["losses"], t["draws"], t["n"]) == (1, 1, 1, 2)
    assert t["profit"] == pytest.approx(-1.5)  # +8,50 −10,00 +0
    assert st["staked"] == 25.0
    assert (st["open"], st["not_sent"], st["no_result"]) == (1, 2, 1)
    assert [p["value"] for p in st["cumulative"]] == pytest.approx([8.5, -1.5, -1.5])
    assert sum(b["profit"] for b in st["timeline"]) == pytest.approx(-1.5)


def test_demo_e_real_nao_se_misturam(client):
    demo = get(client, account="PRACTICE")
    assert (demo["total"]["wins"], demo["total"]["profit"]) == (1, 90.0)
    assert (demo["open"], demo["not_sent"]) == (0, 0)


def test_entrada_manual_aparece_como_linha_propria_e_filtra(client):
    st = get(client, account="REAL")
    labels = {g["key"]: g["label"] for g in st["by_strategy"]}
    assert labels == {"retracao_comando": "Apostila · retração no comando", "manual": "Entrada manual"}
    assert [g["key"] for g in st["by_strategy"]][-1] == "manual"  # depois das estratégias
    only_manual = get(client, account="REAL", strategy="manual")
    assert (only_manual["total"]["draws"], only_manual["total"]["n"]) == (1, 0)
    assert {s["name"] for s in st["strategies"]} == {"retracao_comando", "manual"}


def test_setup_mercado_e_filtro_de_par(client):
    st = get(client, account="REAL")
    assert {g["key"] for g in st["by_setup"]} == {"retracao_comando|gatilho 50%", "retracao_comando|outro setup", "manual|entrada manual"}
    assert {g["key"]: g["n"] + g["draws"] for g in st["by_market"]} == {"Mercado normal": 2, "OTC": 1}
    assert st["assets"] == ["EURUSD-op", "GBPUSD-OTC"]
    otc = get(client, account="REAL", asset="GBPUSD-OTC")
    assert otc["total"]["draws"] == 1 and otc["total"]["wins"] == 0


def test_minimo_para_empatar_usa_o_payout_pago_e_o_do_sinal():
    orders = [
        {"id": 1, "status": "win", "amount": 10, "profit": 8.5, "requested_at": 1, "signal_id": 7, "strategy": "x", "asset": "EURUSD-op"},
        {"id": 2, "status": "loss", "amount": 10, "profit": -10, "requested_at": 2, "signal_id": 8, "strategy": "x", "asset": "EURUSD-op"},
        {"id": 3, "status": "loss", "amount": 10, "profit": -10, "requested_at": 3, "signal_id": None, "strategy": "manual", "asset": "EURUSD-op"},
    ]
    rows = order_rows(orders, {7: {"payout": 0.8, "setup": "a"}, 8: {"payout": 0.9, "setup": "b"}}, default_payout=0.7)
    assert [r["payout"] for r in rows] == pytest.approx([0.85, 0.9, 0.85])  # pago; do sinal; média paga nas vitórias
    assert [r["setup"] for r in rows] == ["a", "b", "entrada manual"]
    assert order_rows(orders[2:], {}, default_payout=0.7)[0]["payout"] == 0.7  # sem vitória nem sinal: o padrão
    assert status_counts(orders + [{"status": "enviando"}, {"status": "erro"}]) == {"open": 1, "not_sent": 1, "no_result": 0}


def test_periodo_deixa_de_fora_ordens_antigas(client):
    order(client.db, "win", amount=10, profit=8.0, ts=NOW - 40 * 86400)
    assert get(client, account="REAL")["total"]["wins"] == 1
    assert get(client, account="REAL", period="geral")["total"]["wins"] == 2
