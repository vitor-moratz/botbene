"""Meta-labeling da retração no comando (docs/metalabel_preregistro.md).

Uso (dentro de backend/, com o venv ativo):
    python -m app.tools.metalabel montar      # replay na base de pesquisa -> data/metalabel/dataset.csv
    python -m app.tools.metalabel relatorio   # quantas entradas há por semana e mercado (não treina nada)

Fase 2 (ambiente de pesquisa, com scikit-learn; só depois das datas do pré-registro):
    python -m app.tools.metalabel treinar  [--mercado op|OTC]   # a partir de 30/11
    python -m app.tools.metalabel conferir [--mercado op|OTC]   # a partir de 05/12, UMA vez
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from app.config import BACKEND_DIR, get_settings
from app.research.dataset import research_db
from app.research.metalabel import BRT, FEATURES, SUB, build_dataset

COLUMNS = ("asset", "market", "decision_ts", "entry_ts", "touch_ts", "direction", "is_v2", "entry_price", "exit_price",
           "result", "result_5s", *FEATURES)


def dataset_path() -> Path:
    return get_settings().resolved_data_dir() / "metalabel" / "dataset.csv"


def cmd_montar(args: argparse.Namespace) -> None:
    db = research_db(get_settings())
    assets = sorted({s["asset"] for s in db.candle_series() if s["timeframe"] == SUB})
    if args.ativos:
        assets = [a for a in assets if a in args.ativos.split(",")]
    rows = build_dataset(db, assets, progress=lambda a, n: print(f"  {a}: {n} entradas", flush=True))
    out = Path(args.saida) if args.saida else dataset_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if isinstance(v, float) and math.isnan(v) else v) for k, v in r.items()})
    print(f"{len(rows)} entradas em {out}")


def cmd_relatorio(args: argparse.Namespace) -> None:
    path = Path(args.entrada) if args.entrada else dataset_path()
    with path.open() as fh:
        rows = list(csv.DictReader(fh))
    g: dict[tuple, list[int]] = defaultdict(lambda: [0, 0, 0])  # ganhos, decididas, com sentimento
    for r in rows:
        if r["result"] not in ("win", "loss"):
            continue
        week = datetime.fromtimestamp(int(r["entry_ts"]), BRT).strftime("%G-S%V")
        for key in ((r["market"], "v1", week), *(((r["market"], "v2", week),) if r["is_v2"] == "1" else ())):
            g[key][0] += r["result"] == "win"
            g[key][1] += 1
            g[key][2] += r["mood_side"] != ""
    print(f"{'mercado':7s} {'estrat':6s} {'semana':9s} {'entradas':>8s} {'acerto':>7s} {'c/ sentim.':>10s}")
    for (market, strat, week), (w, n, m) in sorted(g.items()):
        print(f"{market:7s} {strat:6s} {week:9s} {n:8d} {w / n * 100:6.1f}% {m:10d}")


MODELS = BACKEND_DIR / "app" / "strategies" / "models"
PREREG = BACKEND_DIR.parent / "docs" / "metalabel_preregistro.md"


def model_path(market: str) -> Path:
    return MODELS / f"meta_retracao_{market.lower()}.npz"


def _fmt(st: dict | None) -> str:
    if not st or not st.get("n"):
        return "sem entradas"
    late = f", entrando 5 s depois {st['acerto_5s'] * 100:.1f}%" if st.get("acerto_5s") is not None else ""
    return f"{st['acerto'] * 100:.1f}% de {st['n']} (limite inferior {st['limite_inf'] * 100:.1f}%{late})"


def cmd_treinar(args: argparse.Namespace) -> None:
    from app.research import metalabel_train as mt

    if time.time() < mt.VAL_END:
        raise SystemExit("Antes de 30/11 a validação ainda não aconteceu: o pré-registro não deixa treinar.")
    rows = mt.load_rows(Path(args.entrada) if args.entrada else dataset_path(), args.mercado)
    tr, va, _ = mt.split(rows, mt.DATA_START, mt.TRAIN_END, mt.VAL_END, mt.TEST_END)
    res = mt.train(tr, va)
    out = model_path(args.mercado)
    res.model.save(out)
    report = {"mercado": args.mercado, "escolhido": res.chosen, **res.report}
    (dataset_path().parent / f"treino_{args.mercado.lower()}.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
    print(json.dumps(report, indent=1, ensure_ascii=False))
    print(f"Modelo escolhido: {res.chosen}, gravado em {out}. A conferência só a partir de 05/12, uma vez.")


def cmd_conferir(args: argparse.Namespace) -> None:
    from app.research import metalabel_train as mt
    from app.strategies.meta_model import MetaModel

    lock = dataset_path().parent / f"conferido_{args.mercado.lower()}.json"
    if lock.exists():
        raise SystemExit(f"A conferência de {args.mercado} já foi feita (está em {lock}). Ela só vale uma vez.")
    if time.time() < mt.TEST_END:
        raise SystemExit("A conferência vai até 04/12: só pode rodar a partir de 05/12.")
    model = MetaModel.load(model_path(args.mercado))
    rows = mt.load_rows(Path(args.entrada) if args.entrada else dataset_path(), args.mercado)
    _, _, te = mt.split(rows, mt.DATA_START, mt.TRAIN_END, mt.VAL_END, mt.TEST_END)
    res = mt.evaluate(model, te)
    lock.write_text(json.dumps({"mercado": args.mercado, "em": int(time.time()), **res}, indent=1, ensure_ascii=False))
    lines = [f"\n### Conferência {args.mercado} ({time.strftime('%d/%m/%Y')})", "",
             f"- Filtro principal (limiar {model.threshold:.2f}): {_fmt(res['principal'])}",
             f"- Alta precisão (limiar {model.threshold_hi if model.threshold_hi is not None else '-'}): {_fmt(res['alta_precisao'])}",
             f"- Linha de base, v2 nas mesmas datas: {_fmt(res['v2'])}",
             f"- Todas as entradas da v1: {_fmt(res['todas'])}",
             f"- **Passou:** {'sim' if res['passou'] else 'não'} · **70%:** {'sim' if res['passou_70'] else 'não'}"]
    with PREREG.open("a") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description="Meta-labeling da retração no comando")
    sub = parser.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("montar", help="monta o conjunto de dados pelo replay das velas gravadas")
    m.add_argument("--ativos", default="", help="só estes pares (separados por vírgula)")
    m.add_argument("--saida", default="")
    m.set_defaults(func=cmd_montar)
    r = sub.add_parser("relatorio", help="entradas e acerto por semana e mercado")
    r.add_argument("--entrada", default="")
    r.set_defaults(func=cmd_relatorio)
    for name, func, text in (("treinar", cmd_treinar, "treina e valida (a partir de 30/11)"),
                             ("conferir", cmd_conferir, "conferência única (a partir de 05/12)")):
        c = sub.add_parser(name, help=text)
        c.add_argument("--mercado", default="op", choices=("op", "OTC"))
        c.add_argument("--entrada", default="")
        c.set_defaults(func=func)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
