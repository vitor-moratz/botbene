"""Dicionário Moratz v0: traços neutros de cada vela M1, calculados só com o passado.

- O traço da vela k usa apenas velas até k, inclusive. Nada depois de k entra.
- A "unidade" é a amplitude mediana das 20 velas ANTERIORES a k. Ela deixa o tamanho comparável entre pares e
  horários.
- A vela só fica "pronta" quando as 20 anteriores estão sem buraco (fim de semana, pausa da IQ). Fora disso os
  traços ficam NaN e a vela não entra em nenhuma medida.
- M5 e M15 são montados do M1. Só contam as velas maiores completas e JÁ FECHADAS no fechamento de k.

Sem nomes de mercado (martelo, engolfo, Bollinger...): é o nosso vocabulário. Traço novo entra aqui com data.
"""

from __future__ import annotations

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from app.research.moratz.base import BRT_OFFSET, TF, Serie

VERSAO = "v0 (10/11/2026)"
JANELA = 20
VIAGEM = 5

# nome: (o que mede, como calcula)
DICIONARIO: dict[str, tuple[str, str]] = {
    "tamanho": ("vela grande ou pequena para o momento", "amplitude ÷ unidade"),
    "corpo": ("quanto da vela é corpo", "|fech − abert| ÷ amplitude"),
    "fecho": ("onde fechou dentro da vela", "(fech − mín) ÷ amplitude; 0 = no fundo, 1 = no topo"),
    "pavio_cima": ("sobra acima do corpo", "(máx − maior entre abert e fech) ÷ amplitude"),
    "pavio_baixo": ("sobra abaixo do corpo", "(menor entre abert e fech − mín) ÷ amplitude"),
    "cor": ("subiu, desceu ou ficou parada", "+1 verde, −1 vermelha, 0 parada"),
    "fila": ("velas seguidas da mesma cor", "com sinal: +3 = 3ª verde seguida, −2 = 2ª vermelha seguida"),
    "lugar": ("onde o preço está na faixa das últimas 20 velas", "(fech − mín20) ÷ (máx20 − mín20); 0 = fundo, 1 = topo"),
    "viagem": ("quanto o preço andou nas últimas 5 velas", "(fech da vela k − abert da vela k−4) ÷ unidade"),
    "salto": ("buraco entre o fechamento anterior e a abertura", "(abert_k − fech_k−1) ÷ unidade"),
    "ctx5_cor": ("cor da última M5 fechada", "+1, −1 ou 0"),
    "ctx5_mov": ("quanto andou a última M5 fechada", "(fech − abert da M5) ÷ unidade"),
    "ctx15_cor": ("cor da última M15 fechada", "+1, −1 ou 0"),
    "ctx15_mov": ("quanto andou a última M15 fechada", "(fech − abert da M15) ÷ unidade"),
    "hora": ("hora de Brasília da entrada (abertura de k+1)", "0 a 23"),
    "dia": ("dia da semana da entrada", "0 = segunda … 6 = domingo"),
    "vol_rel": ("volume relativo (só -op; é contagem de ticks)", "volume ÷ mediana das 20 anteriores"),
}
CATEGORICOS = frozenset({"cor", "fila", "hora", "dia", "ctx5_cor", "ctx15_cor"})


def _contiguo(ts: np.ndarray, m: int) -> np.ndarray:
    """True em k quando as velas k−m..k estão todas presentes (sem buraco)."""
    out = np.zeros(len(ts), dtype=bool)
    if len(ts) > m:
        out[m:] = (ts[m:] - ts[:-m]) == m * TF
    return out


def _mediana_anterior(x: np.ndarray, m: int) -> np.ndarray:
    """Mediana de x[k−m..k−1] para cada k (as m velas ANTES de k)."""
    out = np.full(len(x), np.nan)
    if len(x) > m:
        med = np.median(sliding_window_view(x, m), axis=1)  # med[i] = mediana de x[i..i+m−1]
        out[m:] = med[: len(x) - m]
    return out


def _janela(x: np.ndarray, m: int, fn) -> np.ndarray:
    """fn de x[k−m+1..k] (as m velas até k, inclusive)."""
    out = np.full(len(x), np.nan)
    if len(x) >= m:
        out[m - 1:] = fn(sliding_window_view(x, m), axis=1)
    return out


def _fila(ts: np.ndarray, cor: np.ndarray) -> np.ndarray:
    out = np.zeros(len(cor), dtype=np.float64)
    ts_l, cor_l = ts.tolist(), cor.tolist()
    acc = 0
    for i, c in enumerate(cor_l):
        if c == 0:
            acc = 0
        elif i > 0 and ts_l[i] - ts_l[i - 1] == TF and cor_l[i - 1] == c:
            acc += c
        else:
            acc = c
        out[i] = acc
    return out


def _tempo_maior(s: Serie, minutos: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Para cada k: (ok, abertura, fechamento) da última vela de `minutos` completa e já fechada no fechamento
    de k. Uma vela maior que termina às 10:05 só existe para decisões tomadas às 10:05 ou depois."""
    tf = minutos * TF
    n = len(s)
    ok = np.zeros(n, dtype=bool)
    ab = np.full(n, np.nan)
    fe = np.full(n, np.nan)
    if n == 0:
        return ok, ab, fe
    b = s.ts // tf
    inicios = np.flatnonzero(np.r_[True, b[1:] != b[:-1]])
    fins = np.r_[inicios[1:], n] - 1
    ids = b[inicios]
    completo = (fins - inicios + 1) == minutos
    alvo = (s.ts + TF) // tf - 1  # a vela maior que fechou até o fechamento de k
    pos = np.searchsorted(ids, alvo)
    pos_c = np.minimum(pos, len(ids) - 1)
    ok = (pos < len(ids)) & (ids[pos_c] == alvo) & completo[pos_c]
    ab[ok] = s.o[inicios[pos_c[ok]]]
    fe[ok] = s.c[fins[pos_c[ok]]]
    return ok, ab, fe


def tracos(s: Serie) -> dict[str, np.ndarray]:
    """Todos os traços do dicionário, mais `unidade` e `pronta`. Arrays do tamanho da série; NaN = não vale."""
    ts, o, h, l, c, v = s.ts, s.o, s.h, s.l, s.c, s.v  # noqa: E741
    amp = h - l
    unidade = _mediana_anterior(amp, JANELA)
    pronta = _contiguo(ts, JANELA) & (unidade > 0)

    with np.errstate(divide="ignore", invalid="ignore"):
        amp_ok = np.where(amp > 0, amp, np.nan)
        t: dict[str, np.ndarray] = {
            "tamanho": amp / unidade,
            "corpo": np.abs(c - o) / amp_ok,
            "fecho": (c - l) / amp_ok,
            "pavio_cima": (h - np.maximum(o, c)) / amp_ok,
            "pavio_baixo": (np.minimum(o, c) - l) / amp_ok,
        }
        cor = np.sign(c - o)
        t["cor"] = cor.astype(np.float64)
        t["fila"] = _fila(ts, cor.astype(np.int64))
        minimo = _janela(l, JANELA, np.min)
        maximo = _janela(h, JANELA, np.max)
        faixa = maximo - minimo
        t["lugar"] = np.where(faixa > 0, (c - minimo) / faixa, np.nan)
        viagem = np.full(len(s), np.nan)
        if len(s) >= VIAGEM:
            viagem[VIAGEM - 1:] = c[VIAGEM - 1:] - o[: len(s) - VIAGEM + 1]
        t["viagem"] = viagem / unidade
        salto = np.full(len(s), np.nan)
        salto[1:] = o[1:] - c[:-1]
        t["salto"] = salto / unidade
        for minutos in (5, 15):
            ok, ab, fe = _tempo_maior(s, minutos)
            mov = (fe - ab) / unidade
            t[f"ctx{minutos}_cor"] = np.where(ok, np.sign(fe - ab), np.nan)
            t[f"ctx{minutos}_mov"] = np.where(ok, mov, np.nan)
        entrada = ts + TF + BRT_OFFSET  # abertura de k+1, em Brasília
        t["hora"] = ((entrada // 3600) % 24).astype(np.float64)
        t["dia"] = (((entrada // 86400) + 3) % 7).astype(np.float64)  # 01/01/1970 foi quinta-feira
        med_v = _mediana_anterior(v, JANELA)
        t["vol_rel"] = np.where(med_v > 0, v / med_v, np.nan)

    for nome, arr in t.items():
        arr[~pronta] = np.nan
        t[nome] = arr
    t["unidade"] = np.where(pronta, unidade, np.nan)
    t["pronta"] = pronta
    return t
