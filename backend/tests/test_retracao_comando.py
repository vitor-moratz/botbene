"""Retração no comando: arma na vela forte; entra se a seguinte recuar 0,8 ATR nos 15 s iniciais."""

import pytest

from app.market.candle import Candle
from app.strategies.base import Direction
from app.strategies.intra import run_intra
from app.strategies.ldp_apostila import backtest, simulate_entry
from app.strategies.retracao_comando import NAME, RetracaoComando
from tests.helpers import seq

# 16 velas de amplitude 0,10 (ATR = 0,10), depois uma verde forte: amplitude 0,20 (2 ATR), corpo 0,18.
CALM = [(10.00, 10.06, 9.96, 10.02), (10.02, 10.06, 9.96, 10.00)] * 8
STRONG = (10.00, 10.20, 10.00, 10.18)
CANDLES = seq(*CALM, STRONG)
K = len(CANDLES) - 1


def rc_plan(candles, k):
    _, plans = run_intra(candles, [RetracaoComando()])
    return plans[k]


def test_arma_call_depois_da_vela_forte():
    plan = rc_plan(CANDLES, K)
    assert len(plan.armed) == 1
    a = plan.armed[0]
    assert a.strategy == NAME and a.direction is Direction.CALL and a.trigger == "comando"
    assert a.open_offset == pytest.approx(0.08)  # 0,8 × ATR
    assert a.target_ts == CANDLES[K].ts + 60


def test_vela_fraca_nao_arma():
    weak = seq(*CALM, (10.00, 10.20, 9.95, 10.06))  # corpo 24% da amplitude
    plan = rc_plan(weak, K)
    assert not plan.armed and "sem força" in plan.reasons[0]
    small = seq(*CALM, (10.00, 10.12, 10.00, 10.11))  # 1,2 ATR
    assert not rc_plan(small, K).armed


def subs(start, *rows):
    return [Candle(start + 5 * i, o, h, lo, c) for i, (o, h, lo, c) in enumerate(rows)]


def test_marcacao_medida_da_abertura_real():
    a = rc_plan(CANDLES, K).armed[0]
    t = a.target_ts
    # abre em 10.19 (sem GAP: 0,01 <= 10% de 0,20); precisa recuar até 10.11
    entry, why = simulate_entry(a, subs(t, (10.19, 10.19, 10.15, 10.16), (10.16, 10.16, 10.11, 10.12)))
    assert (entry, why) == (10.12, "tocou")
    entry, why = simulate_entry(a, subs(t, (10.19, 10.19, 10.13, 10.14), (10.14, 10.15, 10.12, 10.13)))
    assert (entry, why) == (None, "não buscou a marcação")  # recuou só 0,07


def test_gap_aborta():
    a = rc_plan(CANDLES, K).armed[0]
    assert simulate_entry(a, subs(a.target_ts, (10.25, 10.25, 10.10, 10.12)))[1] == "GAP na abertura"


def test_backtest_resolve_no_fechamento():
    nxt = (10.18, 10.24, 10.09, 10.22)
    candles = CANDLES + seq(nxt, start_ts=CANDLES[-1].ts + 60)
    t = candles[-1].ts
    sub = subs(t, (10.18, 10.18, 10.12, 10.13), (10.13, 10.13, 10.09, 10.10), (10.10, 10.24, 10.10, 10.22))
    _, plans = run_intra(candles, [RetracaoComando()])
    entries = backtest(candles, plans, sub)
    assert len(entries) == 1 and entries[0]["entry_price"] == 10.10 and entries[0]["result"] == "win"
