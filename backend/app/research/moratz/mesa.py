"""Mesa de leitura: lotes de momentos às cegas para o Moratz ler, só do período D.

Cada momento é um instante real de decisão (o fechamento da vela k) com 120 velas M1 até ali e as 5 seguintes,
que a página só mostra depois do palpite. Os momentos são sorteados com semente fixa, repartidos igualmente
entre os pares da trilha, sem buraco nas 125 velas e com o contexto M15 completo. Não há escolha de momentos
"bonitos": sai o que o sorteio der.

Os preços vão como inteiros (em pontos, relativos à primeira abertura) para o arquivo ficar leve.
"""

from __future__ import annotations

import numpy as np

from app.research.moratz.base import TF, quando
from app.research.moratz.medir import Preparada, janela
from app.research.moratz.tracos import DICIONARIO

ANTES = 120
DEPOIS = 5
SEMENTE = 20261110


def casas(preco: float) -> int:
    return 3 if preco > 20 else 5


def _momento(par: str, p: Preparada, k: int) -> dict:
    s = p.serie
    dec = casas(float(s.c[k]))
    esc = 10**dec
    ini, fim = k - ANTES + 1, k + DEPOIS + 1
    base = round(float(s.o[ini]) * esc)
    velas = [
        [round(float(x) * esc) - base for x in vela]
        for vela in zip(s.o[ini:fim], s.h[ini:fim], s.l[ini:fim], s.c[ini:fim], strict=True)
    ]
    regua = {}
    for nome in DICIONARIO:
        x = float(p.t[nome][k])
        regua[nome] = None if np.isnan(x) else round(x, 3)
    return {
        "par": par,
        "ts": int(s.ts[k]),
        "decisao": quando(int(s.ts[k]) + TF),
        "casas": dec,
        "base": base,
        "velas": velas,
        "regua": regua,
        "unidade": round(float(p.t["unidade"][k]) * esc, 2),
        "sobe": int(p.sobe[k]),
        "sobe5": int(p.sobe5[k]) if p.valida5[k] else None,
    }


def momentos(prep: dict[str, Preparada], trilha: str, ini: int, fim: int, quantos: int = 300,
             semente: int | None = None, lote: int = 1) -> list[dict]:
    """Lote 1 usa ids "op-001"; lotes seguintes, "op-L2-001", para as leituras guardadas nunca colidirem."""
    semente = SEMENTE + 100 * (lote - 1) if semente is None else semente
    rng = np.random.default_rng(semente + (0 if trilha == "op" else 1))
    pares = sorted(prep)
    if not pares:
        return []
    cotas = [quantos // len(pares) + (1 if i < quantos % len(pares) else 0) for i in range(len(pares))]
    out = []
    for par, cota in zip(pares, cotas, strict=True):
        p = prep[par]
        n = len(p.serie)
        k = np.arange(n)
        ok = janela(p, ini, fim) & (k >= ANTES - 1) & (k + DEPOIS < n) & ~np.isnan(p.t["ctx15_mov"])
        cand = k[ok]
        cand = cand[(p.serie.ts[cand + DEPOIS] - p.serie.ts[cand - ANTES + 1]) == (ANTES - 1 + DEPOIS) * TF]
        if not len(cand):
            continue
        for kk in rng.choice(cand, size=min(cota, len(cand)), replace=False):
            out.append(_momento(par, p, int(kk)))
    rng.shuffle(out)
    prefixo = trilha if lote == 1 else f"{trilha}-L{lote}"
    for i, m in enumerate(out, 1):
        m["id"] = f"{prefixo}-{i:03d}"
    return out
