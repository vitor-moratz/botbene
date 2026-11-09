"""Modelo do meta-labeling (pegar ou pular uma entrada), para usar no bot só com numpy.

O treino (app/research/metalabel_train.py, com scikit-learn, fora do bot) grava tudo num .npz: nomes das variáveis,
medianas e padronização do treino, os pesos (regressão logística ou árvores) e os limiares escolhidos na validação.
Aqui só se refaz a mesma conta. O treino confere, logo depois de gravar, que esta conta dá a mesma probabilidade do
scikit-learn.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from pathlib import Path

import numpy as np

MISSING_FLAG = "mood_missing"  # 1 quando não há sentimento (antes de 08/11 19:34 ou par sem dado)


class MetaModel:
    def __init__(self, kind: str, names: list[str], medians: np.ndarray, means: np.ndarray, stds: np.ndarray,
                 threshold: float, threshold_hi: float | None = None, coef: np.ndarray | None = None,
                 intercept: float = 0.0, trees: dict | None = None, baseline: float = 0.0) -> None:
        self.kind, self.names = kind, list(names)
        self.medians, self.means, self.stds = medians, means, stds
        self.threshold, self.threshold_hi = threshold, threshold_hi
        self.coef, self.intercept = coef, intercept
        self.trees, self.baseline = trees, baseline

    # ------------------------------------------------------------------ arquivo

    @classmethod
    def load(cls, path: Path) -> MetaModel:
        z = np.load(path, allow_pickle=False)
        kind = str(z["kind"])
        hi = float(z["threshold_hi"])
        trees = None
        if kind == "gbm":
            trees = {k: z[f"tree_{k}"] for k in ("feature", "threshold", "left", "right", "leaf", "value", "offsets")}
        return cls(kind, [str(n) for n in z["names"]], z["medians"], z["means"], z["stds"], float(z["threshold"]),
                   None if math.isnan(hi) else hi, z["coef"] if kind == "logistic" else None, float(z["intercept"]),
                   trees, float(z["baseline"]))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        extra = {}
        if self.kind == "gbm":
            extra = {f"tree_{k}": v for k, v in self.trees.items()}
        np.savez(path, kind=self.kind, names=np.array(self.names), medians=self.medians, means=self.means, stds=self.stds,
                 threshold=self.threshold, threshold_hi=np.nan if self.threshold_hi is None else self.threshold_hi,
                 coef=self.coef if self.coef is not None else np.zeros(0), intercept=self.intercept,
                 baseline=self.baseline, **extra)

    # ------------------------------------------------------------------ conta

    def vector(self, feats: Mapping[str, float]) -> np.ndarray:
        """Variáveis na ordem do treino, com o indicador de sentimento ausente, vazios pela mediana e padronizadas."""
        raw = []
        for n in self.names:
            if n == MISSING_FLAG:
                v = feats.get("mood_side", math.nan)
                raw.append(1.0 if v is None or v != v else 0.0)
            else:
                v = feats.get(n, math.nan)
                raw.append(math.nan if v is None else float(v))
        x = np.array(raw, dtype=float)
        x = np.where(np.isnan(x), self.medians, x)
        return (x - self.means) / self.stds

    def raw_score(self, x: np.ndarray) -> float:
        if self.kind == "logistic":
            return float(x @ self.coef + self.intercept)
        t = self.trees
        total = self.baseline
        for k in range(len(t["offsets"]) - 1):
            node = int(t["offsets"][k])
            while not t["leaf"][node]:
                go_left = x[int(t["feature"][node])] <= t["threshold"][node]
                node = int(t["offsets"][k] + (t["left"][node] if go_left else t["right"][node]))
            total += float(t["value"][node])
        return total

    def prob(self, feats: Mapping[str, float]) -> float:
        """Probabilidade de a entrada ganhar."""
        return 1.0 / (1.0 + math.exp(-self.raw_score(self.vector(feats))))

    def decide(self, feats: Mapping[str, float], high_precision: bool = False) -> tuple[bool, float]:
        p = self.prob(feats)
        q = self.threshold_hi if high_precision and self.threshold_hi is not None else self.threshold
        return p >= q, p
