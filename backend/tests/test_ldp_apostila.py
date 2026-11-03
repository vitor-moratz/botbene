"""Estratégia da apostila: setup armado, vetos, gatilho de 15 s e backtest com velas de 5 s."""

import pytest

from app.market.candle import Candle
from app.strategies.base import Direction
from app.strategies.ldp_apostila import ArmedSetup, backtest, run_plans, simulate_entry
from tests.helpers import T0, random_walk, seq

# 22 velas de aquecimento andando de lado (a última vermelha), depois uma vela de força que rompe
# (nova alta) e um comando único de alta (nova posição). A apostila deve armar CALL na retração
# até o 50% do comando (pág. 27: "caso o candle atual entre na região do comando ele será repelido").
BASE = [(10.00, 10.10, 9.95, 10.05), (10.05, 10.12, 9.98, 10.00)] * 11
SCENARIO = seq(*BASE, (10.05, 10.40, 10.02, 10.35), (10.35, 10.62, 10.35, 10.52))
K = len(SCENARIO) - 1


def plan_at(candles, k):
    _, plans = run_plans(candles)
    return plans[k]


def test_arma_call_na_retracao_ate_o_50_do_comando():
    plan = plan_at(SCENARIO, K)
    assert len(plan.armed) == 1, plan.reasons
    a = plan.armed[0]
    assert a.direction is Direction.CALL and a.trigger == "retracao"
    assert a.level_price == pytest.approx(10.435)
    assert a.target_ts == SCENARIO[K].ts + 60 and a.window_seconds == 15
    assert a.confluences["gatilho"] and a.confluences["contexto"] and a.score >= 3


def test_aquecimento_e_consolidacao_nao_armam():
    _, plans = run_plans(SCENARIO)
    assert all(not p.armed for p in plans[:K])
    assert any("aquecendo" in r for r in plans[5].reasons)
    assert any("consolidação" in r for p in plans[:K] for r in p.reasons)


def test_indecisao_veta():
    # vela seguinte fecha dentro do pavio de cima da anterior: dupla posição (pág. 109)
    candles = SCENARIO + seq((10.52, 10.60, 10.50, 10.58), start_ts=SCENARIO[-1].ts + 60)
    plan = plan_at(candles, K + 1)
    assert not plan.armed
    assert any("indecisão" in r for r in plan.reasons)


def setup_call(level=10.0, target=T0 + 60):
    return ArmedSetup(direction=Direction.CALL, trigger="retracao", level_price=level, level_strength=3,
                      level_sources=["comando_unico:50%"], decision_index=0, decision_ts=target - 60, target_ts=target,
                      window_seconds=15, touch_tol=0.001, prev_close=10.05, prev_range=0.2, gap_tol_pct=0.10,
                      confluences={"gatilho": True})


def subs(*rows, start=T0 + 60):
    return [Candle(start + 5 * i, o, h, lo, c) for i, (o, h, lo, c) in enumerate(rows)]


def test_gatilho_toca_dentro_dos_15s():
    entry, why = simulate_entry(setup_call(), subs((10.05, 10.06, 10.02, 10.03), (10.03, 10.04, 9.999, 10.01)))
    assert (entry, why) == (10.01, "tocou")  # entrada no preço do momento do toque


def test_gatilho_nao_buscou_a_marcacao():
    # tocou só aos 20 s: fora da janela
    candles = subs((10.05, 10.07, 10.03, 10.06), (10.06, 10.08, 10.04, 10.07), (10.07, 10.08, 10.05, 10.06), (10.06, 10.06, 9.99, 10.0))
    assert simulate_entry(setup_call(), candles) == (None, "não buscou a marcação")


def test_gatilho_gap_aborta():
    assert simulate_entry(setup_call(), subs((10.30, 10.31, 9.99, 10.0)))[1] == "GAP na abertura"


def test_backtest_avalia_no_fechamento_da_vela_de_entrada():
    entry_candle = (10.52, 10.70, 10.43, 10.65)
    candles = SCENARIO + seq(entry_candle, start_ts=SCENARIO[-1].ts + 60)
    t = candles[-1].ts
    sub = subs((10.52, 10.53, 10.46, 10.47), (10.47, 10.48, 10.43, 10.44), (10.44, 10.50, 10.44, 10.49), start=t)
    _, plans = run_plans(candles)
    entries = backtest(candles, plans, sub)
    assert len(entries) == 1
    e = entries[0]
    assert e["entry_price"] == 10.44 and e["exit_price"] == 10.65 and e["result"] == "win"


def test_sem_repintura_dos_setups():
    candles = random_walk(400, seed=13)
    _, full = run_plans(candles)
    for cut in (120, 233, 399):
        _, prefix = run_plans(candles[:cut])
        assert [[a.to_dict() for a in p.armed] for p in prefix] == [[a.to_dict() for a in p.armed] for p in full[:cut]]


def test_e_bem_mais_seletiva_que_os_scripts():
    from app.strategies.ldp_v13 import LdpV13

    candles = random_walk(600, seed=8)
    _, plans = run_plans(candles)
    armed = sum(len(p.armed) for p in plans)
    v13 = sum(s is not None for s in LdpV13().scan(candles))
    assert armed < v13
