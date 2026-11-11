"""Medir uma regra: acerto, intervalo, empate, recortes e o sorteio contra a armadilha.

Sorteio: cada sinal recebe o resultado de uma vela sorteada do MESMO par e do MESMO dia (Brasília). Isso mantém o
"clima" do dia (dia de alta, dia de baixa) e apaga só o que a regra diz sobre o momento exato. Se o acaso
consegue o mesmo acerto com frequência, a regra não está enxergando nada.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from contextlib import closing
from pathlib import Path

from app.analytics.stats import breakeven, wilson
from app.research.moratz import base
from app.research.moratz.alvo import cinco, proxima, resultado
from app.research.moratz.base import TF, Serie, dia_brt, quando
from app.research.moratz.regra import aplicar
from app.research.moratz.tracos import tracos

# Portas e réguas do combinado (docs/padrao_moratz/README.md). Fixadas em 10/11/2026, antes de qualquer resultado.
PORTA_D = {"n": 150, "acerto": 0.57, "p": 0.01, "pares": 2 / 3, "sinais_dia": 7.0}
PORTA_E = {"n": 100, "pares": 2 / 3}
FUTURO = {"espia": 100, "corte_espia": 0.50, "veredito": 200, "cai": 0.55, "final": 500}
MIN_PAR = 10  # sinais mínimos de um par para ele contar em "pares acima de 50%"


@dataclass
class Preparada:
    serie: Serie
    t: dict[str, np.ndarray]
    valida: np.ndarray
    sobe: np.ndarray
    valida5: np.ndarray
    sobe5: np.ndarray


def preparar(series: dict[str, Serie]) -> dict[str, Preparada]:
    out = {}
    for par, s in series.items():
        valida, sobe = proxima(s)
        valida5, sobe5 = cinco(s)
        out[par] = Preparada(s, tracos(s), valida, sobe, valida5, sobe5)
    return out


def janela(p: Preparada, ini: int | None, fim: int | None) -> np.ndarray:
    """Velas de decisão dentro de [ini, fim), com a vela de entrada também fechando antes de `fim`
    (nada atravessa a fronteira para o período seguinte)."""
    m = p.valida & p.t["pronta"]
    if ini is not None:
        m &= p.serie.ts >= ini
    if fim is not None:
        m &= p.serie.ts + 2 * TF <= fim
    return m


@dataclass
class Sinais:
    par: np.ndarray
    ts: np.ndarray
    direcao: np.ndarray
    res: np.ndarray
    valida5: np.ndarray
    res5: np.ndarray
    hora: np.ndarray
    saida: np.ndarray  # fechamento da vela de entrada (k+1)

    def __len__(self) -> int:
        return len(self.ts)


def coletar(regra: dict, prep: dict[str, Preparada], ini: int | None, fim: int | None,
            pares: list[str] | None = None) -> Sinais:
    alvo = pares if pares is not None else (regra.get("pares") or sorted(prep))
    partes = []
    for par in alvo:
        if par not in prep:
            continue
        p = prep[par]
        dispara, direcao = aplicar(regra, p.t)
        idx = np.flatnonzero(dispara & janela(p, ini, fim))
        partes.append((
            np.full(len(idx), par, dtype=object), p.serie.ts[idx], direcao[idx],
            resultado(direcao[idx], p.sobe[idx]), p.valida5[idx], resultado(direcao[idx], p.sobe5[idx]),
            p.t["hora"][idx].astype(np.int64), p.serie.c[idx + 1],
        ))
    if not partes:
        vazio = np.array([], dtype=np.int64)
        return Sinais(np.array([], dtype=object), vazio, vazio.astype(np.int8), vazio.astype(np.int8),
                      vazio.astype(bool), vazio.astype(np.int8), vazio, vazio.astype(np.float64))
    cols = [np.concatenate(c) for c in zip(*partes, strict=True)]
    ordem = np.lexsort((cols[0].astype(str), cols[1]))
    return Sinais(*(c[ordem] for c in cols))


def dias_de_mercado(prep: dict[str, Preparada], ini: int | None, fim: int | None, pares: list[str] | None = None) -> int:
    dias: set[int] = set()
    for par in pares or prep:
        if par in prep:
            p = prep[par]
            dias.update(np.unique(dia_brt(p.serie.ts[janela(p, ini, fim)])).tolist())
    return len(dias)


def _acerto(res: np.ndarray) -> tuple[int, int, float | None]:
    w = int((res == 1).sum())
    n = w + int((res == -1).sum())
    return w, n, (w / n if n else None)


def _seq_perdas(res: np.ndarray) -> int:
    melhor = atual = 0
    for r in res.tolist():
        if r == -1:
            atual += 1
            melhor = max(melhor, atual)
        elif r == 1:
            atual = 0
    return melhor


def _queda_max(res: np.ndarray, payout: float) -> float:
    if not len(res):
        return 0.0
    u = np.where(res == 1, payout, np.where(res == -1, -1.0, 0.0)).cumsum()
    return float((np.maximum.accumulate(np.r_[0.0, u])[1:] - u).max())


def resumo(s: Sinais, payout: float, dias: int) -> dict:
    w, n, acerto = _acerto(s.res)
    lo, hi = wilson(w, n)
    por_par = {}
    for par in sorted(set(s.par.tolist())):
        _, pn, pa = _acerto(s.res[s.par == par])
        por_par[par] = {"n": pn, "acerto": pa}
    validos = [d for d in por_par.values() if d["n"] >= MIN_PAR]
    por_hora = {}
    for hora in sorted(set(s.hora.tolist())):
        _, hn, ha = _acerto(s.res[s.hora == hora])
        por_hora[int(hora)] = {"n": hn, "acerto": ha}
    por_dia: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for ts, r in zip(s.ts.tolist(), s.res.tolist(), strict=True):
        if r:
            d = por_dia[quando(ts)[:10]]
            d[0] += r == 1
            d[1] += 1
    _, n5, a5 = _acerto(s.res5[s.valida5])
    return {
        "sinais": len(s),
        "n": n,
        "ganhos": w,
        "empates": int((s.res == 0).sum()),
        "acerto": acerto,
        "ic": [lo, hi],
        "empate": breakeven(payout),
        "payout": payout,
        "unidades": round(w * payout - (n - w), 2),
        "dias": dias,
        "sinais_dia": len(s) / dias if dias else 0.0,
        "pares_validos": len(validos),
        "pares_acima": sum(1 for d in validos if d["acerto"] > 0.5),
        "por_par": por_par,
        "por_hora": por_hora,
        "por_dia": {k: {"n": v[1], "acerto": v[0] / v[1]} for k, v in sorted(por_dia.items())},
        "seq_perdas": _seq_perdas(s.res),
        "queda_max": round(_queda_max(s.res, payout), 2),
        "acerto_5min": a5,
        "n_5min": n5,
    }


def com_entrada_5s(s: Sinais, origem: Path | None = None) -> dict:
    """Execução mais realista, só onde há velas de 5 s (arquivo do servidor, desde ~01/11): entrada no fechamento
    da 1ª vela de 5 s da vela k+1, como o bot entra; saída no fechamento de k+1. Efeitos que vivem só no
    primeiro preço da vela (o "pulo" da cotação) somem aqui."""
    origem = origem or base.get_settings().resolved_data_dir() / "research.sqlite"
    vazio = {"n": 0, "acerto": None, "ic": [0.0, 1.0], "cobertura": 0.0}
    if not len(s) or not origem.exists():
        return vazio
    res = []
    with closing(base._ro(origem)) as con:  # noqa: SLF001 (mesmo pacote; só leitura)
        for par in sorted(set(s.par.tolist())):
            sel = np.flatnonzero(s.par == par)
            alvo = s.ts[sel] + TF
            rows = dict(con.execute(
                "SELECT ts, close FROM candles WHERE asset = ? AND timeframe = 5 AND ts BETWEEN ? AND ?",
                (par, int(alvo.min()), int(alvo.max())),
            ).fetchall())
            for i, ts in zip(sel.tolist(), alvo.tolist(), strict=True):
                entrada = rows.get(ts)
                if entrada is not None:
                    res.append(int(s.direcao[i]) * int(np.sign(s.saida[i] - entrada)))
    if not res:
        return vazio
    arr = np.array(res)
    w, n, a = _acerto(arr)
    return {"n": n, "acerto": a, "ic": list(wilson(w, n)), "cobertura": len(res) / len(s)}


def sorteio(s: Sinais, prep: dict[str, Preparada], ini: int | None, fim: int | None,
            vezes: int = 200, semente: int = 7) -> dict:
    """Em quantos de `vezes` sorteios o acaso fez acerto igual ou melhor que a regra."""
    _, n, acerto = _acerto(s.res)
    if not n:
        return {"vezes": vezes, "p": None, "media": None, "p95": None}
    pool, inicio, tamanho = [], np.zeros(len(s), dtype=np.int64), np.zeros(len(s), dtype=np.int64)
    base = 0
    for par in sorted(set(s.par.tolist())):
        p = prep[par]
        m = janela(p, ini, fim)
        sobe = p.sobe[m]
        dias = dia_brt(p.serie.ts[m])
        cortes = np.flatnonzero(np.r_[True, dias[1:] != dias[:-1]])
        ids = dias[cortes]
        tam = np.diff(np.r_[cortes, len(dias)])
        sel = np.flatnonzero(s.par == par)
        pos = np.searchsorted(ids, dia_brt(s.ts[sel]))
        inicio[sel] = base + cortes[pos]
        tamanho[sel] = tam[pos]
        pool.append(sobe)
        base += len(sobe)
    todos = np.concatenate(pool)
    rng = np.random.default_rng(semente)
    acertos = np.empty(vezes)
    for b in range(vezes):
        idx = inicio + (rng.random(len(s)) * tamanho).astype(np.int64)
        r = s.direcao * todos[idx]
        bw = (r == 1).sum()
        bn = bw + (r == -1).sum()
        acertos[b] = bw / bn if bn else 0.5
    return {
        "vezes": vezes,
        "p": float((1 + (acertos >= acerto).sum()) / (1 + vezes)),
        "media": float(acertos.mean()),
        "p95": float(np.quantile(acertos, 0.95)),
    }


def porta_d(r: dict, sort: dict) -> tuple[bool, list[str]]:
    falhas = []
    if r["n"] < PORTA_D["n"]:
        falhas.append(f"poucos sinais ({r['n']} < {PORTA_D['n']})")
    if r["acerto"] is None or r["acerto"] < PORTA_D["acerto"]:
        falhas.append(f"acerto abaixo de {PORTA_D['acerto']:.0%}")
    if sort.get("p") is None or sort["p"] > PORTA_D["p"]:
        falhas.append("o sorteio fez igual em mais de 1% das vezes")
    if not r["pares_validos"] or r["pares_acima"] < PORTA_D["pares"] * r["pares_validos"]:
        falhas.append(f"só {r['pares_acima']} de {r['pares_validos']} pares acima de 50%")
    if r["sinais_dia"] < PORTA_D["sinais_dia"]:
        falhas.append(f"poucos sinais por dia ({r['sinais_dia']:.1f} < {PORTA_D['sinais_dia']:.0f})")
    return not falhas, falhas


def porta_e(r: dict) -> tuple[bool, list[str]]:
    falhas = []
    if r["n"] < PORTA_E["n"]:
        falhas.append(f"poucos sinais ({r['n']} < {PORTA_E['n']})")
    if r["acerto"] is None or r["acerto"] <= r["empate"]:
        falhas.append(f"acerto não passou do empate ({r['empate']:.1%})")
    if not r["pares_validos"] or r["pares_acima"] < PORTA_E["pares"] * r["pares_validos"]:
        falhas.append(f"só {r['pares_acima']} de {r['pares_validos']} pares acima de 50%")
    return not falhas, falhas


def veredito_futuro(r: dict) -> tuple[str, str]:
    """(código, texto) do placar do futuro, com o placar tampado antes dos marcos combinados."""
    n, acerto, lo = r["n"], r["acerto"], r["ic"][0]
    if n < FUTURO["espia"]:
        return "juntando", f"{n} de {FUTURO['espia']} sinais para a primeira espiada (acerto tampado)"
    if n < FUTURO["veredito"]:
        if acerto < FUTURO["corte_espia"]:
            return "caiu", f"abaixo de 50% com {n} sinais: encerra"
        return "juntando", f"passou da espiada de {FUTURO['espia']}; acerto tampado até {FUTURO['veredito']}"
    if lo > r["empate"]:
        return "passou", f"limite inferior {lo:.1%} acima do empate {r['empate']:.1%} com {n} sinais"
    if acerto < FUTURO["cai"]:
        return "caiu", f"{acerto:.1%} abaixo de {FUTURO['cai']:.0%} com {n} sinais"
    if n >= FUTURO["final"]:
        return "caiu", f"chegou a {n} sinais sem o limite inferior passar do empate"
    return "juntando", f"zona do meio com {n} sinais: junta até {FUTURO['final']}"
