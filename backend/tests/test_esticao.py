"""Esticão rápido: depois de vela grande, entra contra o disparo de 1,5 ATR nos 10 s iniciais."""

import pytest

from app.market.candle import Candle
from app.strategies.base import Direction
from app.strategies.esticao import NAME, Esticao
from app.strategies.intra import INTRA_NAMES, OBSERVE_ONLY, default_intra, run_intra
from app.strategies.ldp_apostila import backtest, simulate_entry
from tests.helpers import seq

# 13 velas de amplitude 0,10 e uma grande de 0,30: ATR das 14 (contando a grande) = 1,6 / 14.
CALM = [(10.00, 10.06, 9.96, 10.02), (10.02, 10.06, 9.96, 10.00)] * 7
BIG = (10.00, 10.30, 10.00, 10.28)
CANDLES = seq(*CALM[:13], BIG)
K = len(CANDLES) - 1
ATR = 1.6 / 14
OFFSET = 1.5 * ATR


def plan_at(candles, k):
    _, plans = run_intra(candles, [Esticao()])
    return plans[k]


def subs_for(target_ts, path):
    """Velas de 5 s a partir de (open, high, low, close)."""
    return [Candle(ts=target_ts + 5 * i, open=o, high=h, low=lo, close=c) for i, (o, h, lo, c) in enumerate(path)]


def test_arma_os_dois_lados_depois_da_vela_grande():
    plan = plan_at(CANDLES, K)
    assert {a.direction for a in plan.armed} == {Direction.PUT, Direction.CALL}
    for a in plan.armed:
        assert a.strategy == NAME and a.trigger == "esticao"
        assert a.window_seconds == 10
        assert a.target_ts == CANDLES[K].ts + 60
        assert a.open_offset == pytest.approx(OFFSET)
        assert a.gap_floor == pytest.approx(0.1 * ATR)
        assert "esticão" in a.setup_label
    put = next(a for a in plan.armed if a.direction is Direction.PUT)
    call = next(a for a in plan.armed if a.direction is Direction.CALL)
    assert put.level_for_open(10.28) == pytest.approx(10.28 + OFFSET)  # PUT em cima da abertura
    assert call.level_for_open(10.28) == pytest.approx(10.28 - OFFSET)  # CALL embaixo


def test_nao_arma_com_vela_normal():
    candles = seq(*CALM[:14])
    plan = plan_at(candles, len(candles) - 1)
    assert plan.armed == []
    assert any("vela pequena" in r for r in plan.reasons)


def test_disparo_para_cima_entra_put_e_ganha_se_voltar():
    target = CANDLES[K].ts + 60
    top = 10.28 + OFFSET + 0.01
    subs = subs_for(target, [(10.28, top, 10.27, top - 0.005), (top - 0.005, top, 10.40, 10.42)])
    put = next(a for a in plan_at(CANDLES, K).armed if a.direction is Direction.PUT)
    call = next(a for a in plan_at(CANDLES, K).armed if a.direction is Direction.CALL)
    entry, why = simulate_entry(put, subs)
    assert why == "tocou" and entry == pytest.approx(top - 0.005)  # preço do fechamento da vela de 5 s do toque
    assert simulate_entry(call, subs)[0] is None  # o lado de baixo não foi tocado
    nxt = Candle(ts=target, open=10.28, high=top, low=10.27, close=10.35)  # voltou até o fim do minuto
    candles = [*CANDLES, nxt]
    _, plans = run_intra(candles, [Esticao()])
    rows = backtest(candles, plans, subs)
    assert [(r["setup"].direction, r["result"]) for r in rows] == [(Direction.PUT, "win")]


def test_gap_na_abertura_aborta():
    target = CANDLES[K].ts + 60
    gap_open = 10.28 + 0.2 * ATR  # passa de 0,1 ATR
    subs = subs_for(target, [(gap_open, gap_open + OFFSET + 0.05, gap_open, gap_open + OFFSET)])
    put = next(a for a in plan_at(CANDLES, K).armed if a.direction is Direction.PUT)
    assert simulate_entry(put, subs) == (None, "GAP na abertura")


def test_disparo_depois_dos_10_s_nao_entra():
    target = CANDLES[K].ts + 60
    calm = (10.28, 10.29, 10.27, 10.28)
    late = (10.28, 10.28 + OFFSET + 0.02, 10.28, 10.28 + OFFSET)
    subs = subs_for(target, [calm, calm, late])  # o disparo só vem entre 10 e 15 s
    put = next(a for a in plan_at(CANDLES, K).armed if a.direction is Direction.PUT)
    assert simulate_entry(put, subs) == (None, "não buscou a marcação")


def test_roda_no_bot_so_para_observar():
    assert NAME in INTRA_NAMES and NAME in OBSERVE_ONLY
    assert any(s.name == NAME for s in default_intra())
