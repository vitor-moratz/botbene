"""Modelo do meta-labeling no bot (só numpy) e as travas da Fase 2 (datas do pré-registro, conferência única)."""

import argparse
import math

import numpy as np
import pytest

from app.strategies.meta_model import MISSING_FLAG, MetaModel


def logistic(threshold=0.6, threshold_hi=0.7):
    names = ["a", "mood_side", MISSING_FLAG]
    return MetaModel("logistic", names, medians=np.array([0.0, 0.5, 0.0]), means=np.array([1.0, 0.5, 0.0]),
                     stds=np.array([2.0, 0.25, 1.0]), threshold=threshold, threshold_hi=threshold_hi,
                     coef=np.array([1.0, 2.0, -0.5]), intercept=0.1)


def test_logistica_padroniza_e_trata_sentimento_ausente():
    m = logistic()
    # a=3 -> (3-1)/2 = 1; mood 0.75 -> (0.75-0.5)/0.25 = 1; com sentimento: flag 0
    assert m.prob({"a": 3.0, "mood_side": 0.75}) == pytest.approx(1 / (1 + math.exp(-(1 + 2 + 0.1))))
    # sem sentimento: mood vira a mediana (0.5 -> 0) e a flag vale 1
    assert m.prob({"a": 3.0, "mood_side": math.nan}) == pytest.approx(1 / (1 + math.exp(-(1 + 0 - 0.5 + 0.1))))
    ok, p = m.decide({"a": 3.0, "mood_side": 0.75})
    assert ok and p > 0.9
    assert m.decide({"a": -3.0, "mood_side": 0.25})[0] is False


def test_arvores_e_arquivo(tmp_path):
    # uma árvore: x0 <= 0 -> -1, senão +1; a outra: folha única +0,5
    trees = {"feature": np.array([0, 0, 0, 0]), "threshold": np.array([0.0, 0, 0, 0]), "left": np.array([1, 0, 0, 0]),
             "right": np.array([2, 0, 0, 0]), "leaf": np.array([False, True, True, True]),
             "value": np.array([0.0, -1.0, 1.0, 0.5]), "offsets": np.array([0, 3, 4])}
    m = MetaModel("gbm", ["x"], np.array([0.0]), np.array([0.0]), np.array([1.0]), threshold=0.55, trees=trees, baseline=0.2)
    assert m.raw_score(np.array([1.0])) == pytest.approx(0.2 + 1.0 + 0.5)
    assert m.raw_score(np.array([-1.0])) == pytest.approx(0.2 - 1.0 + 0.5)
    m.save(tmp_path / "m.npz")
    back = MetaModel.load(tmp_path / "m.npz")
    assert back.kind == "gbm" and back.threshold_hi is None and back.prob({"x": 2.0}) == pytest.approx(m.prob({"x": 2.0}))
    lg = logistic()
    lg.save(tmp_path / "l.npz")
    assert MetaModel.load(tmp_path / "l.npz").prob({"a": 1.0, "mood_side": 0.6}) == pytest.approx(lg.prob({"a": 1.0, "mood_side": 0.6}))


def test_travas_da_fase_2(tmp_path, monkeypatch):
    from app.research import metalabel_train as mt
    from app.tools import metalabel as tool

    monkeypatch.setattr(tool, "dataset_path", lambda: tmp_path / "dataset.csv")
    monkeypatch.setattr(tool.time, "time", lambda: mt.VAL_END - 1)
    with pytest.raises(SystemExit, match="30/11"):
        tool.cmd_treinar(argparse.Namespace(mercado="op", entrada=""))
    monkeypatch.setattr(tool.time, "time", lambda: mt.TEST_END - 1)
    with pytest.raises(SystemExit, match="05/12"):
        tool.cmd_conferir(argparse.Namespace(mercado="op", entrada=""))
    (tmp_path / "conferido_op.json").write_text("{}")
    monkeypatch.setattr(tool.time, "time", lambda: mt.TEST_END + 1)
    with pytest.raises(SystemExit, match="uma vez"):
        tool.cmd_conferir(argparse.Namespace(mercado="op", entrada=""))


def test_limiares_pela_validacao():
    from app.research.metalabel_train import pick_high, pick_main

    rng = np.random.default_rng(1)
    p = rng.uniform(0.4, 0.9, 2000)
    y = (rng.uniform(size=2000) < p).astype(int)  # probabilidade calibrada
    main = pick_main(p, y)
    assert main.threshold is not None and main.n >= 60 and main.lo > 0.6
    high = pick_high(p, y)
    assert high.threshold is not None and high.acc >= 0.70 and high.n >= 40
    assert pick_main(p[:30], y[:30]).threshold is None  # poucas entradas: nenhum limiar vale
