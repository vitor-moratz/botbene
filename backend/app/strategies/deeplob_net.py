"""Rede DeepLOB adaptada às velas de 5 s (E70-IQ-001): só a previsão, em numpy, sem PyTorch.

A rede foi treinada fora do bot (PyTorch) e os pesos ficam em models/deeplob_iq_op.npz. Este arquivo
repete a conta da rede treinada: convoluções que misturam as features, convoluções no tempo, módulo
inception de 3 ramos, LSTM de 64 e a saída. O teste confere a saída contra a do PyTorch.

Entrada: as 100 últimas velas de 5 s (mais a anterior, para o primeiro "fechamento anterior").
Por vela: abertura, máxima, mínima e fechamento menos o fechamento anterior, divididos pelo desvio dos
retornos da própria janela, mais seno e cosseno do segundo do minuto.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

W = 100  # velas de 5 s na janela


def window_features(bars: Sequence[tuple[int, float, float, float, float]]) -> np.ndarray:
    """bars: W+1 velas (ts, abertura, máxima, mínima, fechamento) em ordem; a 1ª só dá o fechamento anterior."""
    a = np.asarray(bars, dtype=np.float64)
    ts, o, h, l, c = a.T
    pc = c[:-1]
    ts, o, h, l, c = ts[1:], o[1:], h[1:], l[1:], c[1:]
    sec = ts % 60
    f = np.c_[o - pc, h - pc, l - pc, c - pc, np.sin(2 * np.pi * sec / 60), np.cos(2 * np.pi * sec / 60)].astype(np.float32)
    sd = f[:, 3].std() + 1e-12
    f[:, :4] = np.clip(f[:, :4] / sd, -10, 10)
    return f


def _bn(x, p, name, eps=1e-5):
    g, b = p[f"{name}.weight"], p[f"{name}.bias"]
    m, v = p[f"{name}.running_mean"], p[f"{name}.running_var"]
    return (x - m[:, None]) / np.sqrt(v[:, None] + eps) * g[:, None] + b[:, None]


def _lrelu(x):
    return np.where(x > 0, x, 0.01 * x)


def _conv(x, w, b):
    """Convolução no tempo com padding "same" do PyTorch (o que sobra vai para a direita). x: (Cin, T)."""
    cout, cin, k, _ = w.shape
    left = (k - 1) // 2
    xp = np.pad(x, ((0, 0), (left, k - 1 - left)))
    T = x.shape[1]
    out = np.zeros((cout, T))
    for j in range(k):
        out += w[:, :, j, 0] @ xp[:, j:j + T]
    return out + b[:, None]


def _block(x, p, conv, bn):
    return _bn(_lrelu(_conv(x, p[f"{conv}.weight"], p[f"{conv}.bias"])), p, bn)


def forward(p: dict, x: np.ndarray) -> float:
    """x: (W, 6) já normalizado. Devolve o logit de "sobe" (antes da calibração)."""
    x = x.astype(np.float64)
    z = p["mix.0.weight"][:, 0, 0, :] @ x.T + p["mix.0.bias"][:, None]  # (16, T)
    z = _bn(_lrelu(z), p, "mix.2")
    z = _block(z, p, "mix.3", "mix.5")
    z = _block(z, p, "mix.6", "mix.8")
    y1 = _block(_block(z, p, "b1.0", "b1.2"), p, "b1.3", "b1.5")
    y2 = _block(_block(z, p, "b2.0", "b2.2"), p, "b2.3", "b2.5")
    zp = np.pad(z, ((0, 0), (1, 1)), constant_values=-np.inf)
    mp = np.maximum(np.maximum(zp[:, :-2], zp[:, 1:-1]), zp[:, 2:])
    y3 = _block(mp, p, "b3.1", "b3.3")
    seq = np.concatenate([y1, y2, y3], 0).T  # (T, 96)
    wih, whh = p["lstm.weight_ih_l0"], p["lstm.weight_hh_l0"]
    bias = p["lstm.bias_ih_l0"] + p["lstm.bias_hh_l0"]
    hid = whh.shape[1]
    h = np.zeros(hid)
    cst = np.zeros(hid)
    pre = seq @ wih.T + bias
    for t in range(seq.shape[0]):
        g = pre[t] + whh @ h
        i, f, gg, o = g[:hid], g[hid:2 * hid], g[2 * hid:3 * hid], g[3 * hid:]
        i, f, o = 1 / (1 + np.exp(-i)), 1 / (1 + np.exp(-f)), 1 / (1 + np.exp(-o))
        cst = f * cst + i * np.tanh(gg)
        h = o * np.tanh(cst)
    return float(p["fc.weight"][0] @ h + p["fc.bias"][0])


def load(path) -> dict:
    with np.load(path, allow_pickle=False) as z:
        return {k: z[k] for k in z.files}


def probability(p: dict, x: np.ndarray) -> float:
    """P(o preço no vencimento ficar acima da entrada), já calibrada (Platt) no dia de calibração."""
    z = float(p["platt_coef"]) * forward(p, x) + float(p["platt_intercept"])
    return 1 / (1 + np.exp(-z))
