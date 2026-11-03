import pytest

from app.analytics.stats import breakeven, summarize, total, wilson
from app.paper import judge, profit_units


def test_judge_call_put_e_empate():
    assert judge("call", 1.0, 1.1) == "win"
    assert judge("call", 1.0, 0.9) == "loss"
    assert judge("put", 1.0, 0.9) == "win"
    assert judge("put", 1.0, 1.1) == "loss"
    assert judge("put", 1.0, 1.0) == "empate"


def test_profit_em_entradas():
    assert profit_units("win", 0.85) == 0.85
    assert profit_units("loss", 0.85) == -1.0
    assert profit_units("empate", 0.85) == 0.0


def test_breakeven_do_plano():
    assert breakeven(0.85) == pytest.approx(0.5405, abs=1e-4)
    assert breakeven(0.80) == pytest.approx(0.5556, abs=1e-4)


def test_wilson_valor_conhecido():
    low, high = wilson(50, 100)
    assert low == pytest.approx(0.4038, abs=1e-3)
    assert high == pytest.approx(0.5962, abs=1e-3)


def test_summarize_ignora_empates_na_taxa():
    rows = [
        {"strategy": "a", "result": "win", "profit": 0.8, "payout": 0.8},
        {"strategy": "a", "result": "loss", "profit": -1.0, "payout": 0.8},
        {"strategy": "a", "result": "empate", "profit": 0.0, "payout": 0.8},
        {"strategy": "b", "result": "win", "profit": 0.8, "payout": 0.8},
    ]
    groups = {g.key: g for g in summarize(rows, lambda r: r["strategy"])}
    assert groups["a"].n == 2 and groups["a"].draws == 1 and groups["a"].winrate == 0.5
    assert groups["a"].profit == pytest.approx(-0.2)
    assert total(rows).n == 3
