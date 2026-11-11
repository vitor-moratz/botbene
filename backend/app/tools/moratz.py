"""Padrão Moratz: o laboratório na linha de comando (docs/padrao_moratz/README.md).

Uso (dentro de backend/, com o venv do bot):
    python -m app.tools.moratz base [--importar]          # o que temos de velas, por trilha e par
    python -m app.tools.moratz mapa [--trilha op|otc]     # mapa da máquina em D, ao lado do sorteio
    python -m app.tools.moratz mesa [--quantos 300]       # momentos às cegas para a mesa de leitura
    python -m app.tools.moratz ver EURUSD-op "14/10/2026 10:32"   # uma vela, com a régua (conversa)
    python -m app.tools.moratz testar regra.json [--variacoes N] [--nota "..."]   # em D, com sorteio
    python -m app.tools.moratz conferir regra.json        # em E, UMA vez por versão da regra
    python -m app.tools.moratz congelar regra.json --versao 1.0
    python -m app.tools.moratz futuro [--versao 1.0] [--importar]
    python -m app.tools.moratz baixar --trilha otc --dias 30 --confirmo   # segundo login na IQ (treino)
    python -m app.tools.moratz pagina                     # caderno + dicionário para republicar a Mesa de Leitura

Tudo o que é testado vai para o caderno (docs/padrao_moratz/caderno.md). Nada aqui manda ordem.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

from app.research.moratz import caderno
from app.research.moratz.base import (
    BRT,
    NOME_TRILHA,
    PAYOUT,
    TF,
    TRILHAS,
    baixar,
    banco_padrao,
    carregar,
    ficha_da_base,
    importar,
    limites,
    pares,
    pasta,
    payout_realizado,
    quando,
    trilha_de,
)
from app.research.moratz.mapa import mapa
from app.research.moratz.medir import (
    FUTURO,
    PORTA_D,
    coletar,
    com_entrada_5s,
    dias_de_mercado,
    porta_d,
    porta_e,
    preparar,
    resumo,
    sorteio,
    veredito_futuro,
)
from app.research.moratz.mesa import momentos
from app.research.moratz.regra import hash_regra, ler
from app.research.moratz.tracos import DICIONARIO


def pct(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:.1f}%".replace(".", ",")


def num(x: float, casas: int = 2) -> str:
    return f"{x:.{casas}f}".replace(".", ",")


def _pares_de_d(trilha: str) -> tuple[list[str], list[str]]:
    """(pares com velas em D, pares que D nunca viu) da trilha, sem os excluídos."""
    ini, fim = limites("D")
    com, sem = [], []
    for par, s in carregar(trilha).items():
        (com if ((s.ts >= ini) & (s.ts < fim)).any() else sem).append(par)
    return com, sem


def _imprimir_resumo(r: dict, titulo: str) -> None:
    lo, hi = r["ic"]
    print(f"\n{titulo}")
    print(f"  sinais: {r['sinais']} ({r['empates']} empates fora) · decididos: {r['n']} · "
          f"{num(r['sinais_dia'], 1)} por dia em {r['dias']} dias de mercado")
    print(f"  acerto: {pct(r['acerto'])}  (IC95 {pct(lo)} a {pct(hi)}) · empate da trilha: {pct(r['empate'])} "
          f"· resultado: {num(r['unidades'])} entradas")
    print(f"  pares acima de 50%: {r['pares_acima']} de {r['pares_validos']} (com ≥ 10 sinais) · "
          f"maior sequência de perdas: {r['seq_perdas']} · queda máxima: {num(r['queda_max'])} entradas")
    if r["n_5min"]:
        print(f"  (só informação) vencimento de 5 min: {pct(r['acerto_5min'])} em {r['n_5min']}")
    if r["por_par"]:
        print("  por par: " + " · ".join(f"{p.replace('-op', '').replace('-OTC', '')} {pct(d['acerto'])} ({d['n']})"
                                        for p, d in r["por_par"].items()))
    if r["por_hora"]:
        print("  por hora: " + " · ".join(f"{h:02d}h {pct(d['acerto'])} ({d['n']})" for h, d in r["por_hora"].items()
                                         if d["n"]))


def _imprimir_5s(r5: dict) -> None:
    if r5["n"]:
        lo, hi = r5["ic"]
        print(f"  com entrada após a 1ª vela de 5 s (como o bot): {pct(r5['acerto'])} (IC95 {pct(lo)} a {pct(hi)}) "
              f"em {r5['n']} sinais ({pct(r5['cobertura'])} dos sinais têm velas de 5 s)")
    else:
        print("  com entrada após a 1ª vela de 5 s: sem velas de 5 s nestas datas")


def _compacto(r: dict) -> dict:
    """O que vai para o caderno (sem os recortes longos)."""
    chaves = ("sinais", "n", "ganhos", "empates", "acerto", "ic", "empate", "unidades", "dias", "sinais_dia",
              "pares_validos", "pares_acima", "seq_perdas", "queda_max", "acerto_5min", "n_5min")
    return {k: r[k] for k in chaves}


def _cabecalho(regra: dict, h: str) -> None:
    print(f"Regra {regra['id']} · versão `{h}` · trilha {NOME_TRILHA[regra['trilha']]} · origem: {regra['origem']}")
    print(f"  \"{regra['texto']}\"")
    for c in regra["condicoes"]:
        faixa = f"em {c['em']}" if "em" in c else " e ".join(
            x for x in (f"≥ {c['min']}" if "min" in c else "", f"≤ {c['max']}" if "max" in c else "") if x)
        print(f"  - {c['traco']} {faixa}")
    print(f"  direção: {regra['direcao']} · vencimento: {regra['vencimento']} s")


def cmd_base(args: argparse.Namespace) -> None:
    if args.importar:
        novos = importar()
        total = sum(novos.values())
        print(f"Importado do arquivo do servidor: {total} velas novas"
              + (" (" + ", ".join(f"{p} +{n}" for p, n in novos.items() if n) + ")" if total else ""))
    print(f"Banco: {banco_padrao()}")
    linhas = ficha_da_base()
    for trilha in TRILHAS:
        print(f"\nTrilha {NOME_TRILHA[trilha]}")
        print(f"  {'par':12s} {'de':16s} {'até':16s} {'velas':>7s} {'em D':>6s} {'em E':>6s} {'buracos':>7s} "
              f"{'longos':>6s} {'paradas':>7s} {'volume':>6s}")
        for x in linhas:
            if x["trilha"] != trilha:
                continue
            fora = "  (fora: paga 0,50)" if x["excluido"] else ""
            dup = f"  ⚠ {x['duplicadas']} duplicadas" if x["duplicadas"] else ""
            print(f"  {x['par']:12s} {quando(x['inicio']):16s} {quando(x['fim']):16s} {x['velas']:7d} "
                  f"{x['velas_D']:6d} {x['velas_E']:6d} {x['buracos']:7d} {x['buracos_longos']:6d} {x['paradas']:7d} "
                  f"{pct(x['volume_pct']):>6s}{fora}{dup}")
    ini, fim = limites("D")
    e_ini, e_fim = limites("E")
    print(f"\nD (descoberta): {quando(ini)} a {quando(fim - 60)} · E (conferência): {quando(e_ini)} a {quando(e_fim - 60)}")
    print("Payout de referência (fixo): " + " · ".join(f"{NOME_TRILHA[t]} {num(PAYOUT[t])} → empate "
                                                       f"{pct(1 / (1 + PAYOUT[t]))}" for t in TRILHAS))
    real = payout_realizado()
    if real:
        print("Payout realizado nas ordens do bot (só informação): " + " · ".join(
            f"{NOME_TRILHA[t]} {num(v, 3)} em {n} ordens ganhas" for t, (v, n) in real.items()))


def cmd_baixar(args: argparse.Namespace) -> None:
    if not args.confirmo:
        sys.exit("Isto abre um SEGUNDO login na IQ (conta de treino) enquanto o bot pode estar ligado. "
                 "Rode de novo com --confirmo se o dono da conta concordou.")
    total = baixar(args.trilha, args.dias, args.pares.split(",") if args.pares else None,
                   progresso=lambda a, tf, n, ts: print(f"  {a}: {n} velas, até {quando(ts)}", flush=True))
    print(f"Baixadas (com repetidas): {sum(total.values())} velas em {len(total)} pares")


def cmd_mapa(args: argparse.Namespace) -> None:
    ini, fim = limites("D")
    trilhas = TRILHAS if args.trilha == "ambas" else (args.trilha,)
    destino = pasta() / "mapa"
    destino.mkdir(parents=True, exist_ok=True)
    for trilha in trilhas:
        com, _ = _pares_de_d(trilha)
        prep = preparar(carregar(trilha, com))
        m = mapa(prep, ini, fim, sorteios=args.sorteios)
        m.update({"trilha": trilha, "periodo": "D", "gerado_em": caderno.agora(), "dicionario": DICIONARIO})
        path = destino / f"mapa_{trilha}.json"
        path.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
        res = m["resumo"]
        print(f"\nTrilha {NOME_TRILHA[trilha]} · D · {m['velas']} velas de {len(m['pares'])} pares")
        print(f"  base: alta {pct(m['base_alta'])} · continua a cor {pct(m['base_continua'])}")
        print(f"  células longe de 50% (≥ {res['longe'] * 100:.0f} pontos, n ≥ {res['min_celula']}), de "
              f"{res['real']['celulas']}:")
        print(f"    % de alta:   real {res['real']['alta']} · sorteio média {num(res['sorteio_media']['alta'], 1)} "
              f"(máx {res['sorteio_max']['alta']} em {res['sorteios']} sorteios)")
        print(f"    % continua:  real {res['real']['continua']} · sorteio média "
              f"{num(res['sorteio_media']['continua'], 1)} (máx {res['sorteio_max']['continua']})")
        destaques = []
        for nome, t in m["real"]["simples"].items():
            for rot, c in zip(t["rotulos"], t["celulas"], strict=True):
                if c["nc"] >= res["min_celula"] and abs(c["continua"] - 0.5) >= 0.02:
                    destaques.append((abs(c["continua"] - 0.5), f"{nome} {rot}: continua {pct(c['continua'])} "
                                      f"({c['nc']}; continua em {c['pares_c'][0]} de {c['pares_c'][1]} pares)"))
        if destaques:
            print("  traços sozinhos mais longe de 50% em 'continua a cor':")
            for _, txt in sorted(destaques, reverse=True)[:8]:
                print(f"    {txt}")
        print(f"  gravado em {path}")


def cmd_mesa(args: argparse.Namespace) -> None:
    ini, fim = limites("D")
    destino = pasta() / "mesa"
    destino.mkdir(parents=True, exist_ok=True)
    for trilha in TRILHAS:
        com, _ = _pares_de_d(trilha)
        prep = preparar(carregar(trilha, com))
        lote = momentos(prep, trilha, ini, fim, quantos=args.quantos, lote=args.lote)
        path = destino / f"momentos_{trilha}.json"
        dados = {"trilha": trilha, "periodo": "D", "lote": args.lote, "gerado_em": caderno.agora(), "momentos": lote}
        path.write_text(json.dumps(dados, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        horas = np.bincount([int(m["regua"]["hora"]) for m in lote], minlength=24)
        print(f"{NOME_TRILHA[trilha]}: {len(lote)} momentos de {len(com)} pares → {path} "
              f"({path.stat().st_size // 1024} KB; horas sem momento: {int((horas == 0).sum())})")


def cmd_ver(args: argparse.Namespace) -> None:
    par = args.par
    trilha = trilha_de(par)
    alvo = datetime.strptime(args.quando, "%d/%m/%Y %H:%M").replace(tzinfo=BRT)
    ts = int(alvo.timestamp())
    s = carregar(trilha, [par]).get(par)
    if s is None:
        sys.exit(f"Sem velas de {par} no banco do laboratório.")
    k = int(np.searchsorted(s.ts, ts))
    if k >= len(s) or s.ts[k] != ts:
        sys.exit(f"Não há vela de {par} começando em {args.quando} (Brasília).")
    prep = preparar({par: s})[par]
    dec = 3 if s.c[k] > 20 else 5
    print(f"{par} · vela das {args.quando} (decisão no fechamento, {quando(ts + TF)})")
    for i in range(max(0, k - 11), k + 1):
        cor = "verde" if s.c[i] > s.o[i] else "vermelha" if s.c[i] < s.o[i] else "parada"
        print(f"  {quando(s.ts[i])[11:]}  abert {s.o[i]:.{dec}f}  máx {s.h[i]:.{dec}f}  mín {s.l[i]:.{dec}f}  "
              f"fech {s.c[i]:.{dec}f}  {cor}{'  ← k' if i == k else ''}")
    print("  régua da vela k: " + " · ".join(
        f"{nome} {num(float(prep.t[nome][k]))}" for nome in DICIONARIO if not np.isnan(prep.t[nome][k])))
    e_ini, e_fim = limites("E")
    if e_ini <= ts < e_fim:
        print("  O que veio depois fica escondido: esta data é do período E (conferência), que cada regra vê uma vez.")
        return
    for i in range(k + 1, min(len(s), k + 6)):
        print(f"  depois {quando(s.ts[i])[11:]}  abert {s.o[i]:.{dec}f}  fech {s.c[i]:.{dec}f}")
    if prep.valida[k]:
        print(f"  vela de entrada (k+1): {'subiu' if prep.sobe[k] > 0 else 'desceu' if prep.sobe[k] < 0 else 'empate'}")


def _medir(regra: dict, periodo_ini: int | None, periodo_fim: int | None, pares_alvo: list[str]) -> tuple[dict, dict]:
    prep = preparar(carregar(regra["trilha"], pares_alvo))
    s = coletar(regra, prep, periodo_ini, periodo_fim)
    r = resumo(s, PAYOUT[regra["trilha"]], dias_de_mercado(prep, periodo_ini, periodo_fim))
    return r, {"prep": prep, "sinais": s}


def cmd_testar(args: argparse.Namespace) -> None:
    regra = ler(args.regra)
    h = hash_regra(regra)
    _cabecalho(regra, h)
    ini, fim = limites("D")
    com, _ = _pares_de_d(regra["trilha"])
    alvo = [p for p in (regra["pares"] or com) if p in com]
    r, extra = _medir(regra, ini, fim, alvo)
    sort = sorteio(extra["sinais"], extra["prep"], ini, fim, vezes=200)
    _imprimir_resumo(r, f"Em D (descoberta, {quando(ini)[:10]} a {quando(fim - 60)[:10]}), {len(alvo)} pares:")
    if sort["p"] is not None:
        print(f"  sorteio: o acaso fez igual ou melhor em {pct(sort['p'])} das {sort['vezes']} vezes "
              f"(média {pct(sort['media'])}, 95% dos sorteios até {pct(sort['p95'])})")
    ok, falhas = porta_d(r, sort)
    print("\nPorta para a conferência: " + ("PASSOU." if ok else "não passou: " + "; ".join(falhas) + "."))
    print(f"  (régua: n ≥ {PORTA_D['n']}, acerto ≥ {pct(PORTA_D['acerto'])}, sorteio ≤ 1%, ≥ 2/3 dos pares acima "
          f"de 50%, ≥ {PORTA_D['sinais_dia']:.0f} sinais/dia)")
    caderno.registrar({
        "tipo": "teste_D", "regra_id": regra["id"], "hash": h, "trilha": regra["trilha"], "texto": regra["texto"],
        "origem": regra["origem"], "condicoes": regra["condicoes"], "direcao": regra["direcao"],
        "variacoes": args.variacoes, "resultado": _compacto(r), "sorteio": sort, "porta": ok, "falhas": falhas,
        **({"nota": args.nota} if args.nota else {}),
    })
    print("\nRegistrado no caderno (docs/padrao_moratz/caderno.md).")


def _trava(h: str) -> Path:
    return pasta() / "conferidas" / f"conferido_{h}.json"


def cmd_conferir(args: argparse.Namespace) -> None:
    regra = ler(args.regra)
    h = hash_regra(regra)
    _cabecalho(regra, h)
    trava = _trava(h)
    if trava.exists():
        antigo = json.loads(trava.read_text(encoding="utf-8"))
        sys.exit(f"\nEsta versão da regra já foi conferida em {antigo['quando']}: acerto "
                 f"{pct(antigo['resultado']['acerto'])} em {antigo['resultado']['n']}. O E se vê uma vez só; "
                 "mudar a regra agora vira outra versão.")
    passou_d = [e for e in caderno.ler() if e["tipo"] == "teste_D" and e.get("hash") == h and e.get("porta")]
    if not passou_d:
        sys.exit("\nEsta versão ainda não passou a porta em D (rode `testar` antes). O E fica guardado para quem passa.")
    ini, fim = limites("E")
    com, novos = _pares_de_d(regra["trilha"])
    alvo = [p for p in (regra["pares"] or com) if p in com]
    r, extra = _medir(regra, ini, fim, alvo)
    _imprimir_resumo(r, f"Em E (conferência, {quando(ini)[:10]} a {quando(fim - 60)[:10]}), pares de D:")
    r5 = com_entrada_5s(extra["sinais"])
    _imprimir_5s(r5)
    r_novos = None
    if novos and not regra["pares"]:
        r_novos, _ = _medir(regra, ini, fim, novos)
        _imprimir_resumo(r_novos, f"Em E, pares que D nunca viu ({len(novos)}; só informação):")
    ok, falhas = porta_e(r)
    print("\nPorta para congelar: " + ("PASSOU." if ok else "não passou: " + "; ".join(falhas) + "."))
    registro = {"quando": caderno.agora(), "hash": h, "regra": regra, "resultado": _compacto(r),
                "entrada_5s": r5, "pares_novos": _compacto(r_novos) if r_novos else None, "porta": ok,
                "falhas": falhas}
    trava.parent.mkdir(parents=True, exist_ok=True)
    trava.write_text(json.dumps(registro, ensure_ascii=False, indent=1), encoding="utf-8")
    caderno.registrar({
        "tipo": "conferencia_E", "regra_id": regra["id"], "hash": h, "trilha": regra["trilha"], "texto": regra["texto"],
        "resultado": _compacto(r), "entrada_5s": r5, "porta": ok, "falhas": falhas,
        **({"nota": f"pares novos: {pct(r_novos['acerto'])} em {r_novos['n']}"} if r_novos else {}),
    })
    print("Registrado no caderno e travado: esta versão não roda de novo em E.")


def cmd_congelar(args: argparse.Namespace) -> None:
    regra = ler(args.regra)
    h = hash_regra(regra)
    trava = _trava(h)
    if not trava.exists() or not json.loads(trava.read_text(encoding="utf-8"))["porta"]:
        sys.exit("Só congela a versão que passou a porta em E (rode `conferir` antes).")
    versoes = caderno.PASTA / "versoes"
    nome = f"v{args.versao}"
    if (versoes / f"{nome}.json").exists():
        sys.exit(f"A {nome} já existe. Cada versão congelada é para sempre: use outro número.")
    agora_ts = int(datetime.now(BRT).timestamp())
    desde = (agora_ts // TF + 1) * TF  # primeira vela que começa depois do congelamento
    lista = regra["pares"] or pares(trilha=regra["trilha"])
    congelada = {"versao": nome, "hash": h, "regra": regra, "pares": lista, "congelada_em": quando(agora_ts),
                 "futuro_desde_ts": desde, "payout": PAYOUT[regra["trilha"]], "regua": FUTURO}
    versoes.mkdir(parents=True, exist_ok=True)
    (versoes / f"{nome}.json").write_text(json.dumps(congelada, ensure_ascii=False, indent=1), encoding="utf-8")
    texto = [
        f"# Padrão Moratz {nome}: pré-registro",
        "",
        f"**Congelada em {quando(agora_ts)} (Brasília), antes de qualquer vela do futuro.** Nada daqui muda depois. "
        "Mudar a regra é começar outra versão, com outro futuro.",
        "",
        "## A regra",
        "",
        f"> {regra['texto']}",
        "",
        f"- Trilha: {NOME_TRILHA[regra['trilha']]} · direção: {regra['direcao']} · vencimento: 1 min "
        "(entrada na abertura da vela seguinte)",
        *[f"- {c['traco']}: " + (f"em {c['em']}" if "em" in c else " e ".join(
            x for x in (f"≥ {c['min']}" if "min" in c else "", f"≤ {c['max']}" if "max" in c else "") if x))
          for c in regra["condicoes"]],
        f"- Pares: {', '.join(lista)}",
        f"- Hash: `{h}`",
        "",
        "## Critérios no futuro (velas a partir de " + quando(desde) + ")",
        "",
        f"- Até {FUTURO['espia']} sinais, o acerto fica tampado.",
        f"- Aos {FUTURO['espia']}: abaixo de {FUTURO['corte_espia']:.0%} encerra.",
        f"- Aos {FUTURO['veredito']}: passa se o limite inferior de Wilson (95%) ficar acima do empate "
        f"({pct(1 / (1 + PAYOUT[regra['trilha']]))}); cai abaixo de {FUTURO['cai']:.0%}; no meio, junta até "
        f"{FUTURO['final']}.",
        "- Passou: entra no bot em Observar para conferir o ao vivo. Sem dinheiro antes disso.",
        "",
        "## Resultado",
        "",
        "_(preencher pelo `futuro`, sem apagar nada acima)_",
        "",
    ]
    (versoes / f"{nome}.md").write_text("\n".join(texto), encoding="utf-8")
    caderno.registrar({"tipo": "congelamento", "regra_id": regra["id"], "hash": h, "trilha": regra["trilha"],
                       "texto": regra["texto"], "nota": f"{nome}; futuro a partir de {quando(desde)}"})
    print(f"Congelada como {nome}. O futuro conta a partir de {quando(desde)}. Pré-registro: {versoes / (nome + '.md')}")


def cmd_futuro(args: argparse.Namespace) -> None:
    if args.importar:
        novos = importar()
        print(f"Importado do arquivo do servidor: {sum(novos.values())} velas novas")
    versoes = caderno.PASTA / "versoes"
    arquivos = sorted(versoes.glob("v*.json")) if versoes.exists() else []
    if args.versao:
        arquivos = [a for a in arquivos if a.stem == f"v{args.versao}"]
    if not arquivos:
        sys.exit("Nenhuma versão congelada ainda.")
    registros = caderno.ler()
    for arq in arquivos:
        v = json.loads(arq.read_text(encoding="utf-8"))
        regra = v["regra"]
        r, extra = _medir(regra, v["futuro_desde_ts"], None, v["pares"])
        codigo, texto = veredito_futuro(r)
        print(f"\n{v['versao']} · {NOME_TRILHA[regra['trilha']]} · congelada em {v['congelada_em']}")
        print(f"  \"{regra['texto']}\"")
        print(f"  {r['sinais']} sinais ({r['n']} decididos) em {r['dias']} dias · {num(r['sinais_dia'], 1)} por dia")
        if r["n"] < FUTURO["veredito"] and r["sinais_dia"] > 0:
            falta = (FUTURO["veredito"] - r["n"]) / r["sinais_dia"]
            print(f"  faltam ~{falta:.0f} dias de mercado para {FUTURO['veredito']} sinais")
        print(f"  {codigo.upper()}: {texto}")
        if codigo != "juntando" or r["n"] >= FUTURO["veredito"]:
            lo, hi = r["ic"]
            print(f"  acerto {pct(r['acerto'])} (IC95 {pct(lo)} a {pct(hi)}) · empate {pct(r['empate'])}")
            _imprimir_5s(com_entrada_5s(extra["sinais"]))
        marco = next((m for m in (FUTURO["final"], FUTURO["veredito"], FUTURO["espia"]) if r["n"] >= m), None)
        ja = any(e["tipo"] == "futuro" and e.get("hash") == v["hash"] and e.get("marco") == marco for e in registros)
        if marco and not ja:
            caderno.registrar({"tipo": "futuro", "regra_id": regra["id"], "hash": v["hash"], "trilha": regra["trilha"],
                               "texto": regra["texto"], "marco": marco, "veredito": codigo, "detalhe": texto,
                               **({"resultado": _compacto(r)} if marco >= FUTURO["veredito"] or codigo == "caiu" else {})})
            print(f"  marco de {marco} sinais registrado no caderno")


def cmd_pagina(args: argparse.Namespace) -> None:
    """Dados que a Mesa de Leitura mostra além dos momentos e do mapa: o caderno e o dicionário."""
    destino = pasta() / "mesa"
    destino.mkdir(parents=True, exist_ok=True)
    dados = {"gerado_em": caderno.agora(), "entradas": caderno.ler(),
             "dicionario": {k: list(v) for k, v in DICIONARIO.items()},
             "empate": {t: 1 / (1 + PAYOUT[t]) for t in TRILHAS}}
    path = destino / "caderno.json"
    path.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    print(f"{len(dados['entradas'])} registros do caderno → {path}")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m app.tools.moratz", description="Padrão Moratz: o laboratório")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("base", help="velas do laboratório por trilha e par")
    b.add_argument("--importar", action="store_true", help="antes, traz o M1 novo do arquivo do servidor")
    b.set_defaults(fn=cmd_base)
    bx = sub.add_parser("baixar", help="completa pela IQ (segundo login, conta de treino)")
    bx.add_argument("--trilha", choices=TRILHAS, required=True)
    bx.add_argument("--dias", type=int, default=30)
    bx.add_argument("--pares", default="")
    bx.add_argument("--confirmo", action="store_true", help="o dono da conta concordou com o segundo login")
    bx.set_defaults(fn=cmd_baixar)
    m = sub.add_parser("mapa", help="mapa da máquina em D, ao lado do sorteio")
    m.add_argument("--trilha", choices=(*TRILHAS, "ambas"), default="ambas")
    m.add_argument("--sorteios", type=int, default=20)
    m.set_defaults(fn=cmd_mapa)
    me = sub.add_parser("mesa", help="momentos às cegas para a mesa de leitura")
    me.add_argument("--quantos", type=int, default=300)
    me.add_argument("--lote", type=int, default=1, help="lote 2 em diante: outro sorteio e ids que não colidem")
    me.set_defaults(fn=cmd_mesa)
    v = sub.add_parser("ver", help="uma vela com a régua (para a conversa)")
    v.add_argument("par")
    v.add_argument("quando", help='"dd/mm/aaaa HH:MM", começo da vela em Brasília')
    v.set_defaults(fn=cmd_ver)
    t = sub.add_parser("testar", help="mede a regra em D, com sorteio, e registra no caderno")
    t.add_argument("regra")
    t.add_argument("--variacoes", type=int, default=1, help="quantas variações foram olhadas para chegar nesta")
    t.add_argument("--nota", default="")
    t.set_defaults(fn=cmd_testar)
    c = sub.add_parser("conferir", help="mede em E, uma vez por versão")
    c.add_argument("regra")
    c.set_defaults(fn=cmd_conferir)
    cg = sub.add_parser("congelar", help="congela a versão: a partir daí só o futuro conta")
    cg.add_argument("regra")
    cg.add_argument("--versao", required=True)
    cg.set_defaults(fn=cmd_congelar)
    pg = sub.add_parser("pagina", help="caderno e dicionário para a Mesa de Leitura (data/moratz/mesa/caderno.json)")
    pg.set_defaults(fn=cmd_pagina)
    f = sub.add_parser("futuro", help="placar das versões congeladas, só com velas posteriores")
    f.add_argument("--versao", default="")
    f.add_argument("--importar", action="store_true")
    f.set_defaults(fn=cmd_futuro)
    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
