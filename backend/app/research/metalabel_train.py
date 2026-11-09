"""Fase 2 do meta-labeling: treino, validação e conferência, exatamente como em docs/metalabel_preregistro.md.

Precisa de scikit-learn, que NÃO fica no ambiente do bot. Rode no ambiente de pesquisa (`backend/.venv-pesquisa`, veja o
pré-registro). O resultado é um .npz que o bot usa só com numpy (app/strategies/meta_model.py).
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np

from app.research.metalabel import BRT, FEATURES
from app.strategies.meta_model import MISSING_FLAG, MetaModel


def _ts(y: int, m: int, d: int) -> int:
    return int(datetime(y, m, d, tzinfo=BRT).timestamp())


# Datas do pré-registro (início de cada parte, horário de Brasília). Não mudar: mudar é estudo novo.
DATA_START = _ts(2026, 11, 2)
TRAIN_END = _ts(2026, 11, 23)
VAL_END = _ts(2026, 11, 30)
TEST_END = _ts(2026, 12, 5)
GRID = [round(0.50 + 0.01 * i, 2) for i in range(31)]  # 0,50 a 0,80
MIN_N_MAIN, MIN_N_HI, HI_ACC = 60, 40, 0.70
BREAKEVEN = 0.543  # payout de 84%
NAMES = [*FEATURES, MISSING_FLAG]


def wilson_lo(w: int, n: int, z: float = 1.96) -> float:
    if n == 0:
        return 0.0
    p = w / n
    d = 1 + z * z / n
    return ((p + z * z / (2 * n)) - z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / d


# ---------------------------------------------------------------------- dados


def load_rows(path: Path, market: str) -> list[dict]:
    """Entradas decididas (ganhou/perdeu) do mercado, a partir do início do estudo."""
    with Path(path).open() as fh:
        rows = [r for r in csv.DictReader(fh)
                if r["market"] == market and r["result"] in ("win", "loss") and int(r["entry_ts"]) >= DATA_START]
    for r in rows:
        r["entry_ts"] = int(r["entry_ts"])
        r["is_v2"] = int(r["is_v2"])
        for f in FEATURES:
            r[f] = float(r[f]) if r.get(f, "") != "" else math.nan
    return sorted(rows, key=lambda r: r["entry_ts"])


def split(rows: list[dict], start: int, train_end: int, val_end: int, test_end: int) -> tuple[list, list, list]:
    tr = [r for r in rows if start <= r["entry_ts"] < train_end]
    va = [r for r in rows if train_end <= r["entry_ts"] < val_end]
    te = [r for r in rows if val_end <= r["entry_ts"] < test_end]
    return tr, va, te


def raw_matrix(rows: list[dict]) -> np.ndarray:
    x = np.array([[r[f] for f in FEATURES] for r in rows], dtype=float).reshape(len(rows), len(FEATURES))
    flag = np.isnan(x[:, FEATURES.index("mood_side")]).astype(float)[:, None]
    return np.hstack([x, flag])


def labels(rows: list[dict]) -> np.ndarray:
    return np.array([r["result"] == "win" for r in rows], dtype=int)


@dataclass
class Prep:
    medians: np.ndarray
    means: np.ndarray
    stds: np.ndarray

    @classmethod
    def fit(cls, raw: np.ndarray) -> Prep:
        med = np.nanmedian(np.where(np.isnan(raw).all(axis=0), 0.0, raw), axis=0)
        med = np.where(np.isnan(med), 0.0, med)
        filled = np.where(np.isnan(raw), med, raw)
        mean, std = filled.mean(axis=0), filled.std(axis=0)
        return cls(med, mean, np.where(std > 0, std, 1.0))

    def transform(self, raw: np.ndarray) -> np.ndarray:
        return (np.where(np.isnan(raw), self.medians, raw) - self.means) / self.stds


# ---------------------------------------------------------------------- limiares


@dataclass
class Pick:
    threshold: float | None
    wins: int = 0
    n: int = 0

    @property
    def acc(self) -> float:
        return self.wins / self.n if self.n else 0.0

    @property
    def lo(self) -> float:
        return wilson_lo(self.wins, self.n)


def pick_main(p: np.ndarray, y: np.ndarray, min_n: int = MIN_N_MAIN) -> Pick:
    best = Pick(None)
    for q in GRID:
        sel = p >= q
        n = int(sel.sum())
        if n < min_n:
            continue
        cand = Pick(q, int(y[sel].sum()), n)
        if best.threshold is None or cand.lo > best.lo:
            best = cand
    return best


def pick_high(p: np.ndarray, y: np.ndarray, min_n: int = MIN_N_HI, acc: float = HI_ACC) -> Pick:
    for q in GRID:
        sel = p >= q
        n = int(sel.sum())
        if n >= min_n and y[sel].sum() / n >= acc:
            return Pick(q, int(y[sel].sum()), n)
    return Pick(None)


# ---------------------------------------------------------------------- treino


@dataclass
class TrainResult:
    model: MetaModel
    chosen: str
    report: dict = field(default_factory=dict)


def _export(kind: str, est, prep: Prep, main: Pick, high: Pick) -> MetaModel:
    common = dict(names=NAMES, medians=prep.medians, means=prep.means, stds=prep.stds, threshold=main.threshold,
                  threshold_hi=high.threshold)
    if kind == "logistic":
        return MetaModel("logistic", coef=est.coef_.ravel().astype(float), intercept=float(est.intercept_[0]), **common)
    feats, thr, left, right, leaf, value, offsets = [], [], [], [], [], [], [0]
    for it in est._predictors:  # noqa: SLF001 - a conta é conferida contra predict_proba logo abaixo
        nodes = it[0].nodes
        feats += list(nodes["feature_idx"]); thr += list(nodes["num_threshold"])
        left += list(nodes["left"]); right += list(nodes["right"])
        leaf += list(nodes["is_leaf"]); value += list(nodes["value"])
        offsets.append(offsets[-1] + len(nodes))
    trees = {"feature": np.array(feats, dtype=np.int64), "threshold": np.array(thr, dtype=float),
             "left": np.array(left, dtype=np.int64), "right": np.array(right, dtype=np.int64),
             "leaf": np.array(leaf, dtype=bool), "value": np.array(value, dtype=float), "offsets": np.array(offsets, dtype=np.int64)}
    return MetaModel("gbm", trees=trees, baseline=float(np.asarray(est._baseline_prediction).ravel()[0]), **common)  # noqa: SLF001


def train(train_rows: list[dict], val_rows: list[dict]) -> TrainResult:
    """Os dois modelos do pré-registro; fica o de maior limite inferior de Wilson na validação."""
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression

    raw_tr, raw_va = raw_matrix(train_rows), raw_matrix(val_rows)
    prep = Prep.fit(raw_tr)
    xtr, xva = prep.transform(raw_tr), prep.transform(raw_va)
    ytr, yva = labels(train_rows), labels(val_rows)
    estimators = {
        "logistic": LogisticRegression(C=1.0, max_iter=2000),
        "gbm": HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=30,
                                              early_stopping=False, random_state=0),
    }
    report, models = {}, {}
    for kind, est in estimators.items():
        est.fit(xtr, ytr)
        p = est.predict_proba(xva)[:, 1]
        main, high = pick_main(p, yva), pick_high(p, yva)
        if main.threshold is None:
            report[kind] = {"limiar": None}
            continue
        model = _export(kind, est, prep, main, high)
        check = np.array([model.raw_score(x) for x in xva])
        mine = 1 / (1 + np.exp(-check))
        if not np.allclose(mine, p, atol=1e-9):
            raise RuntimeError(f"a conta em numpy do modelo {kind} não bate com o scikit-learn")
        models[kind] = model
        report[kind] = {"limiar": main.threshold, "acerto": main.acc, "n": main.n, "limite_inf": main.lo,
                        "limiar_70": high.threshold, "acerto_70": high.acc, "n_70": high.n}
    if not models:
        raise RuntimeError("nenhum modelo teve limiar com entradas suficientes na validação")
    chosen = max(models, key=lambda k: report[k]["limite_inf"])
    v2 = [r for r in val_rows if r["is_v2"]]
    report["v2_validacao"] = {"acerto": sum(r["result"] == "win" for r in v2) / max(len(v2), 1), "n": len(v2)}
    report["treino_n"], report["validacao_n"] = len(train_rows), len(val_rows)
    return TrainResult(models[chosen], chosen, report)


# ---------------------------------------------------------------------- conferência


def evaluate(model: MetaModel, test_rows: list[dict]) -> dict:
    """Uma única passada na conferência: filtro principal, alta precisão, linha de base (v2) e entrada 5 s depois."""
    p = np.array([model.prob(r) for r in test_rows])
    y = labels(test_rows)

    def stats(sel: np.ndarray) -> dict:
        n = int(sel.sum())
        w = int(y[sel].sum())
        late = [r["result_5s"] for r, s in zip(test_rows, sel) if s and r.get("result_5s") in ("win", "loss")]
        return {"n": n, "acerto": w / n if n else 0.0, "limite_inf": wilson_lo(w, n),
                "acerto_5s": sum(x == "win" for x in late) / len(late) if late else None}

    main = stats(p >= model.threshold)
    v2 = stats(np.array([bool(r["is_v2"]) for r in test_rows]))
    high = stats(p >= model.threshold_hi) if model.threshold_hi is not None else None
    passed = main["n"] >= 100 and main["limite_inf"] > BREAKEVEN and main["acerto"] >= v2["acerto"] + 0.03
    passed_hi = bool(high and high["n"] >= 60 and high["acerto"] >= HI_ACC)
    return {"principal": main, "alta_precisao": high, "v2": v2, "todas": stats(np.ones(len(y), dtype=bool)),
            "passou": passed, "passou_70": passed_hi}
