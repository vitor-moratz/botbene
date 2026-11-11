"""Contar por ciclo de gale na tela Desempenho (10/11/2026): a mesma regra do painel, sem misturar com quem não usa gale."""

import time

import pytest

from app.analytics.orders import cycle_breakeven, cycle_limit, cycle_rows
from app.analytics.timeline import period_start
from tests.test_config import make_client

NOW = int(time.time())
T = max(NOW - 3600, period_start("hoje") + 1)
BB, RET = "bb_rci", "retracao_comando"


def row(result, gale=0, strategy=BB, profit=None, amount=2.0, ts=0):
    if profit is None:
        profit = round(amount * 0.83, 2) if result == "win" else -amount if result == "loss" else 0.0
    return {"result": result, "profit": profit, "payout": 0.83, "entry_ts": ts, "strategy": strategy, "setup": "s",
            "asset": "EURUSD-op", "is_otc": False, "amount": amount, "option_type": "binary", "gale": gale}


def test_ciclos_ganho_perdido_e_quem_nao_usa_gale():
    rows = [row("loss", 0), row("loss", 1, amount=4.41), row("win", 2, amount=9.73),       # ganho no G2: 1 vitória
            row("win", 0),                                                               # ganho na entrada
            row("loss", 0, strategy=RET),                                               # retração: passa como está
            row("loss", 0), row("loss", 1, amount=4.41), row("loss", 2, amount=9.73)]    # perdido: 1 derrota (3 ordens)
    out = cycle_rows(rows, {BB}, 2)
    bb = [r for r in out if r["strategy"] == BB]
    assert [r["result"] for r in bb] == ["win", "win", "loss"] and [r["losses"] for r in bb] == [2, 0, 3]
    assert round(sum(r["profit"] for r in out), 2) == round(sum(r["profit"] for r in rows), 2)  # o dinheiro não muda
    assert [r["result"] for r in out if r["strategy"] == RET] == ["loss"]


def test_ciclo_no_meio():
    rows = [row("win", 0), row("loss", 0), row("loss", 1, amount=4.41)]
    assert [r["result"] for r in cycle_rows(rows, {BB}, 2)] == ["win", "loss"]   # parou no meio: perdido
    assert [r["result"] for r in cycle_rows(rows, {BB}, 2, open_tail=True)] == ["win"]  # o bot ainda está nele
    assert [r["result"] for r in cycle_rows(rows, {BB}, 2, open_tail={BB})] == ["win"]
    assert [r["result"] for r in cycle_rows(rows, {BB}, 2, open_tail={RET})] == ["win", "loss"]  # é outra que está no meio


def test_um_ciclo_por_estrategia():
    rows = [row("loss", 0), row("loss", 0, strategy=RET), row("win", 1, amount=4.41), row("win", 1, strategy=RET, amount=4.41)]
    out = cycle_rows(rows, {BB, RET}, 2)
    assert [(r["strategy"], r["result"]) for r in out] == [(BB, "win"), (RET, "win")]  # a entrada da outra não fecha o ciclo
    assert [r["profit"] for r in out] == [round(-2 + 4.41 * 0.83, 2)] * 2


def test_minimos_do_ciclo():
    assert round(cycle_breakeven(2, 2, 0.83), 3) == 0.907  # % de ciclos ganhos: 16,14 ÷ (16,14 + 1,66)
    assert round(cycle_limit(2, 2, 0.83), 1) == 10.7


def order(db, status, gale=0, amount=2.0, strategy=BB, ts=T):
    profit = round(amount * 0.83, 2) if status == "win" else -amount if status == "loss" else 0.0
    return db.add_order(asset="EURUSD-op", timeframe=60, strategy=strategy, direction="call", amount=amount, account="REAL",
                        status=status, requested_at=ts, profit=profit, gale=gale)


@pytest.fixture
def client(tmp_path):
    with make_client(tmp_path) as c:
        db = c.app.state.db
        seq = [("loss", 0, 2.0, BB), ("loss", 1, 4.41, BB), ("win", 2, 9.73, BB), ("win", 0, 2.0, BB),
               ("loss", 0, 2.0, RET), ("loss", 0, 2.0, BB), ("loss", 1, 4.41, BB), ("loss", 2, 9.73, BB), ("win", 0, 2.0, RET)]
        for i, (st, g, amt, strat) in enumerate(seq):
            order(db, st, g, amt, strat, ts=T + 60 * i)
        c.put("/api/config", json={"martingale": True, "gale_levels": 2, "gale_strategies": [BB]})
        yield c


def test_desempenho_por_ordem_continua_igual(client):
    st = client.get("/api/stats/orders?period=hoje&account=REAL").json()
    assert (st["total"]["wins"], st["total"]["losses"]) == (3, 6) and st["cycle"] is None  # por ordem: tudo


def test_desempenho_por_ciclo(client):
    st = client.get("/api/stats/orders?period=hoje&account=REAL&ciclo=true").json()
    assert (st["total"]["wins"], st["total"]["losses"]) == (2, 1)  # só a Bollinger: 2 ciclos ganhos, 1 perdido (3 ordens)
    c = st["cycle"]
    assert c["strategies"] == [BB] and (c["won"], c["lost_cycles"], c["losses"]) == (2, 1, 3)
    assert c["every_n"] == 3.0 and c["limit_n"] == 10.7 and round(st["breakeven"], 3) == 0.907
    assert round(st["total"]["winrate"], 3) == 0.667
    groups = {g["key"]: g for g in st["by_strategy"]}
    assert (groups[BB]["wins"], groups[BB]["losses"]) == (2, 1) and round(groups[BB]["breakeven"], 3) == 0.907
    assert (groups[RET]["wins"], groups[RET]["losses"]) == (1, 1) and groups[RET]["breakeven"] < 0.6  # sem gale: por ordem
    assert st["staked"] == round(2 + 4.41 + 9.73 + 2 + 2 + 4.41 + 9.73, 2)  # só as ordens de verdade da Bollinger


def test_sem_martingale_o_ciclo_nao_muda_nada(client):
    client.put("/api/config", json={"martingale": False})
    st = client.get("/api/stats/orders?period=hoje&account=REAL&ciclo=true").json()
    assert st["cycle"] is None and (st["total"]["wins"], st["total"]["losses"]) == (3, 6)
