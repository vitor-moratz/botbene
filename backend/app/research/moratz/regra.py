"""Uma hipótese do Padrão Moratz escrita como regra exata (JSON), no vocabulário do dicionário.

Modelo do formato (docs/padrao_moratz/regras/modelo.json):
    {
      "id": "M-000",
      "trilha": "op",
      "texto": "Depois de uma vela grande que fecha colada no topo, a próxima desce.",
      "origem": "olho",
      "condicoes": [
        {"traco": "tamanho", "min": 2.0},
        {"traco": "fecho", "min": 0.9},
        {"traco": "hora", "em": [9, 10, 11]}
      ],
      "direcao": "contra_cor",
      "vencimento": 60,
      "pares": null
    }

- Condição: {"traco", "min"?, "max"?} (inclusive) ou {"traco", "em": [valores]} para traços de categoria.
- Direção: "call", "put", "contra_cor" (contra a cor da vela k) ou "a_favor_cor".
- Vela que não tem o traço (NaN) não entra. Vela parada (cor 0) não entra nas direções relativas à cor.
- O hash da regra só leva o que muda a decisão (trilha, condições, direção, vencimento, pares). Reescrever o texto
  não muda o hash; mudar qualquer número muda, e vira outra versão no caderno.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from app.research.moratz.base import EXCLUIDOS, TRILHAS, trilha_de
from app.research.moratz.tracos import DICIONARIO

DIRECOES = ("call", "put", "contra_cor", "a_favor_cor")
ORIGENS = ("olho", "mapa", "misto")
VENCIMENTOS = (60,)


def ler(path: str | Path) -> dict:
    return validar(json.loads(Path(path).read_text(encoding="utf-8")))


def validar(regra: dict) -> dict:
    erros = []
    for campo in ("id", "trilha", "texto", "condicoes", "direcao"):
        if campo not in regra:
            erros.append(f"falta o campo '{campo}'")
    if erros:
        raise ValueError("Regra incompleta: " + "; ".join(erros))
    if regra["trilha"] not in TRILHAS:
        erros.append(f"trilha '{regra['trilha']}' não existe (use op ou otc)")
    if regra["direcao"] not in DIRECOES:
        erros.append(f"direção '{regra['direcao']}' não existe (use {', '.join(DIRECOES)})")
    if regra.get("origem", "olho") not in ORIGENS:
        erros.append(f"origem '{regra.get('origem')}' não existe (use {', '.join(ORIGENS)})")
    if regra.get("vencimento", 60) not in VENCIMENTOS:
        erros.append("a v0 só mede vencimento de 60 s")
    if not isinstance(regra["condicoes"], list) or not regra["condicoes"]:
        erros.append("precisa de pelo menos uma condição")
    else:
        for i, cond in enumerate(regra["condicoes"], 1):
            nome = cond.get("traco")
            if nome not in DICIONARIO:
                erros.append(f"condição {i}: traço '{nome}' não está no dicionário")
            if "em" in cond:
                if not isinstance(cond["em"], list) or not cond["em"]:
                    erros.append(f"condição {i}: 'em' precisa ser uma lista com valores")
            elif "min" not in cond and "max" not in cond:
                erros.append(f"condição {i}: use 'min', 'max' ou 'em'")
            extra = set(cond) - {"traco", "min", "max", "em"}
            if extra:
                erros.append(f"condição {i}: campos desconhecidos {sorted(extra)}")
    pares = regra.get("pares")
    if pares is not None:
        for par in pares:
            if trilha_de(par) != regra.get("trilha"):
                erros.append(f"o par {par} não é da trilha {regra.get('trilha')}")
            if par in EXCLUIDOS:
                erros.append(f"o par {par} está fora do estudo (paga 0,50)")
    if erros:
        raise ValueError("Regra inválida: " + "; ".join(erros))
    return {"origem": "olho", "vencimento": 60, "pares": None, **regra}


def hash_regra(regra: dict) -> str:
    nucleo = {
        "trilha": regra["trilha"],
        "condicoes": sorted((json.dumps(c, sort_keys=True) for c in regra["condicoes"])),
        "direcao": regra["direcao"],
        "vencimento": regra.get("vencimento", 60),
        "pares": sorted(regra["pares"]) if regra.get("pares") else None,
    }
    return hashlib.sha256(json.dumps(nucleo, sort_keys=True).encode()).hexdigest()[:12]


def aplicar(regra: dict, t: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    """(dispara, direcao) para cada vela: dispara = todas as condições valem; direcao +1 CALL, −1 PUT."""
    n = len(t["pronta"])
    dispara = t["pronta"].copy()
    for cond in regra["condicoes"]:
        x = t[cond["traco"]]
        with np.errstate(invalid="ignore"):
            ok = ~np.isnan(x)
            if "em" in cond:
                ok &= np.isin(x, np.asarray(cond["em"], dtype=np.float64))
            if "min" in cond:
                ok &= x >= cond["min"]
            if "max" in cond:
                ok &= x <= cond["max"]
        dispara &= ok
    cor = np.nan_to_num(t["cor"], nan=0.0).astype(np.int8)
    if regra["direcao"] == "call":
        direcao = np.ones(n, dtype=np.int8)
    elif regra["direcao"] == "put":
        direcao = -np.ones(n, dtype=np.int8)
    elif regra["direcao"] == "contra_cor":
        direcao = -cor
        dispara &= cor != 0
    else:
        direcao = cor.copy()
        dispara &= cor != 0
    return dispara, direcao
