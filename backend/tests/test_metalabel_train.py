"""Fase 2 do meta-labeling com dados sintéticos: treina, exporta, a conta em numpy bate com o scikit-learn e a conferência
compara com a v2. Precisa de scikit-learn (ambiente de pesquisa); no ambiente do bot estes testes são pulados."""

import csv
import math
import random

import pytest

pytest.importorskip("sklearn")

from app.research import metalabel_train as mt  # noqa: E402
from app.research.metalabel import FEATURES  # noqa: E402
from app.strategies.meta_model import MetaModel  # noqa: E402

DAY = 86400


def fake_rows(n=3000, seed=4):
    """Entradas com um padrão plantado: comando curto + toque rápido ganha 70%; o resto, 47%. Sentimento só na 2ª metade."""
    rnd = random.Random(seed)
    span = mt.TEST_END - mt.DATA_START
    rows = []
    for i in range(n):
        f = {k: rnd.gauss(0, 1) for k in FEATURES}
        f["run_length"] = float(rnd.choice((1, 2, 3, 4)))
        f["touch_sec"] = float(rnd.choice((5, 10, 15)))
        ts = mt.DATA_START + int(span * i / n)
        if ts < mt.DATA_START + span // 2:
            f["mood_side"] = f["mood_chg_fav"] = f["mood_age"] = math.nan
        good = f["run_length"] <= 2 and f["touch_sec"] <= 10
        win = rnd.random() < (0.70 if good else 0.47)
        rows.append({"entry_ts": ts, "market": "op", "is_v2": int(f["run_length"] <= 2), "result": "win" if win else "loss",
                     "result_5s": "win" if win else "loss", **f})
    return rows


def test_treina_exporta_e_confere(tmp_path):
    rows = fake_rows()
    path = tmp_path / "ds.csv"
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["entry_ts", "market", "is_v2", "result", "result_5s", *FEATURES])
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if isinstance(v, float) and math.isnan(v) else v) for k, v in r.items()})
    loaded = mt.load_rows(path, "op")
    tr, va, te = mt.split(loaded, mt.DATA_START, mt.TRAIN_END, mt.VAL_END, mt.TEST_END)
    assert tr and va and te and tr[-1]["entry_ts"] < va[0]["entry_ts"] < te[0]["entry_ts"]
    res = mt.train(tr, va)  # dentro: a conta em numpy é conferida contra predict_proba
    assert res.chosen in ("logistic", "gbm") and res.model.threshold is not None
    res.model.save(tmp_path / "m.npz")
    back = MetaModel.load(tmp_path / "m.npz")
    assert back.prob(te[0]) == pytest.approx(res.model.prob(te[0]))
    out = mt.evaluate(back, te)
    assert out["principal"]["n"] > 0
    assert out["principal"]["acerto"] > out["todas"]["acerto"]  # o filtro achou o padrão plantado
    assert set(out) >= {"principal", "alta_precisao", "v2", "todas", "passou", "passou_70"}
