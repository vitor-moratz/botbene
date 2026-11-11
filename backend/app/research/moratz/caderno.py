"""Caderno do Padrão Moratz: toda tentativa fica registrada, inclusive as que falharam.

`caderno.jsonl` (uma linha por registro, só cresce) vai para o git; `caderno.md` é gerado a partir dele.
Contar quantas ideias foram testadas é o que impede de achar que a 40ª tentativa "deu certo" por mérito.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from app.config import BACKEND_DIR
from app.research.moratz.base import BRT, NOME_TRILHA

PASTA = BACKEND_DIR.parent / "docs" / "padrao_moratz"
TIPOS = {
    "marco": "Marco",
    "leitura": "Leitura do olho",
    "teste_D": "Teste em D (descoberta)",
    "conferencia_E": "Conferência em E (uma vez)",
    "congelamento": "Congelamento",
    "futuro": "Futuro",
}


def agora() -> str:
    return datetime.now(BRT).strftime("%d/%m/%Y %H:%M")


def ler(pasta: Path | None = None) -> list[dict]:
    path = (pasta or PASTA) / "caderno.jsonl"
    if not path.exists():
        return []
    return [json.loads(linha) for linha in path.read_text(encoding="utf-8").splitlines() if linha.strip()]


def registrar(entrada: dict, pasta: Path | None = None) -> dict:
    pasta = pasta or PASTA
    if entrada.get("tipo") not in TIPOS:
        raise ValueError(f"tipo de registro desconhecido: {entrada.get('tipo')}")
    entrada = {"quando": agora(), **entrada}
    pasta.mkdir(parents=True, exist_ok=True)
    with (pasta / "caderno.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entrada, ensure_ascii=False, sort_keys=True) + "\n")
    (pasta / "caderno.md").write_text(gerar_md(ler(pasta)), encoding="utf-8")
    return entrada


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:.1f}%".replace(".", ",")


def _linha_resultado(r: dict) -> str:
    if not r:
        return ""
    lo, hi = r.get("ic", [None, None])
    partes = [f"{r.get('n', 0)} sinais decididos", f"acerto {_pct(r.get('acerto'))} (IC95 {_pct(lo)} a {_pct(hi)})",
              f"empate {_pct(r.get('empate'))}"]
    if r.get("sinais_dia") is not None:
        partes.append(f"{r['sinais_dia']:.1f} sinais/dia".replace(".", ","))
    if r.get("pares_validos"):
        partes.append(f"{r['pares_acima']} de {r['pares_validos']} pares acima de 50%")
    return " · ".join(partes)


def gerar_md(entradas: list[dict]) -> str:
    testes = [e for e in entradas if e["tipo"] == "teste_D"]
    variacoes = sum(int(e.get("variacoes", 1)) for e in testes)
    conferidas = [e for e in entradas if e["tipo"] == "conferencia_E"]
    congeladas = [e for e in entradas if e["tipo"] == "congelamento"]
    leituras = [e for e in entradas if e["tipo"] == "leitura"]
    linhas = [
        "# Caderno do Padrão Moratz",
        "",
        "Gerado por `python -m app.tools.moratz` a partir de `caderno.jsonl`. Não edite à mão: o registro só cresce.",
        "",
        "## Placar das tentativas",
        "",
        "| | -op | OTC |",
        "|---|---|---|",
    ]
    for rotulo, grupo, peso in (
        ("Testes em D (regras)", testes, False),
        ("Variações testadas em D", testes, True),
        ("Conferências em E", conferidas, False),
        ("Versões congeladas", congeladas, False),
        ("Lotes de leitura registrados", leituras, False),
    ):
        cont = {t: sum((int(e.get("variacoes", 1)) if peso else 1) for e in grupo if e.get("trilha") == t)
                for t in ("op", "otc")}
        linhas.append(f"| {rotulo} | {cont['op']} | {cont['otc']} |")
    linhas += ["", f"Total de variações já olhadas em D: **{variacoes}**. Quanto maior, mais desconfiança com "
               "um resultado bonito em D: é para isso que existem o E e o futuro.", "", "## Registros", ""]
    if not entradas:
        linhas.append("_Nenhum registro ainda._")
    for e in entradas:
        trilha = NOME_TRILHA.get(e.get("trilha", ""), "")
        titulo = " · ".join(x for x in (e["quando"], TIPOS[e["tipo"]], e.get("regra_id", ""),
                                        f"`{e['hash']}`" if e.get("hash") else "", trilha) if x)
        linhas += [f"### {titulo}", ""]
        if e.get("texto"):
            linhas += [f"> {e['texto']}", ""]
        if e.get("resultado"):
            linhas += [_linha_resultado(e["resultado"]), ""]
        if e.get("sorteio", {}).get("p") is not None:
            s = e["sorteio"]
            linhas += [f"Sorteio: o acaso fez igual ou melhor em {_pct(s['p'])} das {s['vezes']} vezes "
                       f"(média {_pct(s['media'])}).", ""]
        if e.get("porta") is not None:
            linhas += [("Passou a porta." if e["porta"] else "Não passou a porta: " + "; ".join(e.get("falhas", []))
                        + "."), ""]
        if e.get("veredito"):
            linhas += [f"Veredito: **{e['veredito']}**. {e.get('detalhe', '')}".strip(), ""]
        if e.get("nota"):
            linhas += [f"Nota: {e['nota']}", ""]
    return "\n".join(linhas).rstrip() + "\n"
