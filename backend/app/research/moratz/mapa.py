"""Mapa da máquina: a minha leitura das velas com o vocabulário do dicionário, sem regra nenhuma ainda.

Para cada traço (em faixas) e para pares de traços (grades), mostra o que veio na vela seguinte:
- % de alta: quantas vezes a vela de entrada (k+1) fechou acima da abertura;
- % que continua: quantas vezes ela seguiu a cor da vela k (o contrário é "virou").
Tudo ao lado do SORTEIO: o mesmo mapa com os resultados embaralhados dentro de cada par e dia, onde não existe
padrão. Uma célula longe de 50% só interessa se o sorteio não costuma produzir células assim.

Faixas dos traços contínuos = quintis do período medido (cada faixa com ~20% das velas).
"""

from __future__ import annotations

from itertools import combinations

import numpy as np

from app.analytics.stats import wilson
from app.research.moratz.base import dia_brt
from app.research.moratz.medir import Preparada, janela
from app.research.moratz.tracos import CATEGORICOS, DICIONARIO

CONTINUOS = ("tamanho", "corpo", "fecho", "pavio_cima", "pavio_baixo", "lugar", "viagem", "salto",
             "ctx5_mov", "ctx15_mov", "vol_rel")
NA_GRADE = ("tamanho", "corpo", "fecho", "lugar", "viagem", "ctx5_mov", "ctx15_mov", "fila")
MIN_CELULA = 300  # células menores não entram na contagem de "longe de 50%"
LONGE = 0.05  # 5 pontos acima ou abaixo de 50%
MIN_PAR_CELULA = 30
DIAS = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")


def juntar(prep: dict[str, Preparada], ini: int | None, fim: int | None) -> dict[str, np.ndarray]:
    """Todas as velas de decisão do período, de todos os pares da trilha, numa tabela só."""
    colunas: dict[str, list] = {"par": [], "bloco": [], "sobe": []}
    for nome in DICIONARIO:
        colunas[nome] = []
    for i, par in enumerate(sorted(prep)):
        p = prep[par]
        m = janela(p, ini, fim)
        colunas["par"].append(np.full(int(m.sum()), i, dtype=np.int64))
        colunas["bloco"].append(i * 1_000_000 + dia_brt(p.serie.ts[m]))
        colunas["sobe"].append(p.sobe[m])
        for nome in DICIONARIO:
            colunas[nome].append(p.t[nome][m])
    out = {k: np.concatenate(v) if v else np.array([]) for k, v in colunas.items()}
    out["npares"] = np.array(len(prep))
    return out


def embaralhar(tab: dict[str, np.ndarray], rng: np.random.Generator) -> np.ndarray:
    """Os resultados (sobe) trocados de lugar dentro de cada bloco par+dia; os traços ficam onde estão."""
    ordem = np.lexsort((rng.random(len(tab["bloco"])), tab["bloco"]))
    base = np.argsort(tab["bloco"], kind="stable")
    out = np.empty_like(tab["sobe"])
    out[base] = tab["sobe"][ordem]
    return out


def faixas(nome: str, x: np.ndarray, bordas: list[float] | None = None) -> tuple[np.ndarray, list[str], list[float]]:
    """(faixa de cada vela, rótulos, bordas). Faixa −1 = sem valor."""
    ok = ~np.isnan(x)
    b = np.full(len(x), -1, dtype=np.int64)
    if nome in CATEGORICOS:
        if nome == "fila":
            rot = ["≤ −4"] + [f"{v:+d}" if v else "0" for v in range(-3, 4)] + ["≥ +4"]
            b[ok] = np.clip(x[ok], -4, 4).astype(np.int64) + 4
            return b, rot, []
        if nome == "hora":
            vals = list(range(24))
            rot = [f"{h:02d}h" for h in vals]
        elif nome == "dia":
            vals = list(range(7))
            rot = list(DIAS)
        else:
            vals = [-1, 0, 1]
            rot = ["vermelha", "parada", "verde"]
        b[ok] = np.searchsorted(np.array(vals, dtype=np.float64), x[ok])
        return b, rot, []
    if bordas is None:
        bordas = np.unique(np.quantile(x[ok], [0.2, 0.4, 0.6, 0.8])).tolist() if ok.any() else []
    b[ok] = np.searchsorted(np.array(bordas), x[ok], side="right")
    lim = ["mín", *[f"{v:.2f}" for v in bordas], "máx"]
    rot = [f"{lim[i]} a {lim[i + 1]}" for i in range(len(bordas) + 1)]
    return b, rot, bordas


def _celulas(chave: np.ndarray, nb: int, sobe: np.ndarray, cor: np.ndarray, par: np.ndarray,
             npares: int) -> list[dict]:
    dec = (chave >= 0) & (sobe != 0)
    n = np.bincount(chave[dec], minlength=nb)
    up = np.bincount(chave[dec & (sobe == 1)], minlength=nb)
    cm = dec & ~np.isnan(cor) & (cor != 0)
    cn = np.bincount(chave[cm], minlength=nb)
    cw = np.bincount(chave[cm & (sobe == np.nan_to_num(cor))], minlength=nb)
    pp = np.bincount(chave[dec] * npares + par[dec], minlength=nb * npares).reshape(nb, npares)
    pu = np.bincount((chave * npares + par)[dec & (sobe == 1)], minlength=nb * npares).reshape(nb, npares)
    pcn = np.bincount((chave * npares + par)[cm], minlength=nb * npares).reshape(nb, npares)
    pcw = np.bincount((chave * npares + par)[cm & (sobe == np.nan_to_num(cor))], minlength=nb * npares).reshape(nb, npares)
    out = []
    for i in range(nb):
        validos = pp[i] >= MIN_PAR_CELULA
        acima = int(((pu[i] / np.maximum(pp[i], 1)) > 0.5)[validos].sum())
        validos_c = pcn[i] >= MIN_PAR_CELULA
        acima_c = int(((pcw[i] / np.maximum(pcn[i], 1)) > 0.5)[validos_c].sum())
        lo, hi = wilson(int(up[i]), int(n[i]))
        clo, chi = wilson(int(cw[i]), int(cn[i]))
        out.append({
            "n": int(n[i]),
            "alta": round(up[i] / n[i], 4) if n[i] else None,
            "ic": [round(lo, 4), round(hi, 4)],
            "nc": int(cn[i]),
            "continua": round(cw[i] / cn[i], 4) if cn[i] else None,
            "icc": [round(clo, 4), round(chi, 4)],
            "pares": [acima, int(validos.sum())],
            "pares_c": [acima_c, int(validos_c.sum())],
        })
    return out


def _longe(celulas: list[dict]) -> tuple[int, int]:
    alta = sum(1 for c in celulas if c["n"] >= MIN_CELULA and abs(c["alta"] - 0.5) >= LONGE)
    cont = sum(1 for c in celulas if c["nc"] >= MIN_CELULA and abs(c["continua"] - 0.5) >= LONGE)
    return alta, cont


def _tracos_da_trilha(tab: dict[str, np.ndarray]) -> list[str]:
    nomes = []
    for nome in DICIONARIO:
        x = tab[nome]
        if len(x) and (~np.isnan(x)).mean() > 0.5:  # vol_rel some no OTC (volume zerado)
            nomes.append(nome)
    return nomes


def separar(tab: dict[str, np.ndarray]) -> dict[str, tuple[np.ndarray, list[str], list[float]]]:
    """Faixas de cada traço da trilha, calculadas uma vez (o sorteio não mexe nos traços)."""
    return {nome: faixas(nome, tab[nome]) for nome in _tracos_da_trilha(tab)}


def montar(tab: dict[str, np.ndarray], sobe: np.ndarray | None = None,
           bins: dict[str, tuple[np.ndarray, list[str], list[float]]] | None = None) -> dict:
    """Mapa completo (traço a traço e grades) para uma coluna de resultados (a real ou uma sorteada)."""
    sobe = tab["sobe"] if sobe is None else sobe
    bins = bins if bins is not None else separar(tab)
    npares = int(tab["npares"])
    cor = tab["cor"]
    simples = {}
    for nome, (b, rot, bordas) in bins.items():
        simples[nome] = {"rotulos": rot, "bordas": bordas,
                         "celulas": _celulas(b, len(rot), sobe, cor, tab["par"], npares)}
    grades = []
    for x, y in combinations([n for n in NA_GRADE if n in bins], 2):
        bx, nx = bins[x][0], len(bins[x][1])
        by, ny = bins[y][0], len(bins[y][1])
        chave = np.where((bx >= 0) & (by >= 0), bx * ny + by, -1)
        grades.append({"x": x, "y": y, "nx": nx, "ny": ny,
                       "celulas": _celulas(chave, nx * ny, sobe, cor, tab["par"], npares)})
    return {"simples": simples, "grades": grades}


def contar_longe(m: dict) -> dict:
    todas = [c for t in m["simples"].values() for c in t["celulas"]] + [c for g in m["grades"] for c in g["celulas"]]
    alta, cont = _longe(todas)
    return {"celulas": len(todas), "alta": alta, "continua": cont}


def mapa(prep: dict[str, Preparada], ini: int | None, fim: int | None, sorteios: int = 20, semente: int = 11) -> dict:
    tab = juntar(prep, ini, fim)
    bins = separar(tab)
    real = montar(tab, bins=bins)
    rng = np.random.default_rng(semente)
    exemplo = None
    contagens = []
    for i in range(sorteios):
        m = montar(tab, embaralhar(tab, rng), bins)
        contagens.append(contar_longe(m))
        if i == 0:
            exemplo = m
    dec = tab["sobe"] != 0
    cm = dec & ~np.isnan(tab["cor"]) & (tab["cor"] != 0)
    return {
        "velas": int(len(tab["sobe"])),
        "pares": sorted(prep),
        "base_alta": float((tab["sobe"][dec] == 1).mean()) if dec.any() else None,
        "base_continua": float((tab["sobe"][cm] == tab["cor"][cm]).mean()) if cm.any() else None,
        "real": real,
        "sorteio": exemplo,
        "resumo": {
            "real": contar_longe(real),
            "sorteio_media": {k: float(np.mean([c[k] for c in contagens])) for k in ("alta", "continua")},
            "sorteio_max": {k: int(max(c[k] for c in contagens)) for k in ("alta", "continua")},
            "sorteios": sorteios,
            "min_celula": MIN_CELULA,
            "longe": LONGE,
        },
    }
