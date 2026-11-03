"""Relatório vela a vela: classe da vela (apostila), estruturas e sinais dos dois scripts portados.

Serve para conferir o port contra os scripts rodando na IQ Option: abra o mesmo ativo e
horário na plataforma e compare as setas com as colunas `ldp_v13` e `wiki_pro_v21`.

Uso:
    python -m app.tools.signals_report --csv ../data/candles/EURUSD_60.csv
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from app.ldp.engine import LdpEngine
from app.market.csvio import read_candles_csv
from app.strategies.ldp_v13 import LdpV13
from app.strategies.wiki_pro_v21 import WikiProV21
from app.tools.common import fmt_time


def _fmt(value: float | None) -> str:
    return "" if value is None else f"{value:.6f}"


def build_rows(candles: list) -> list[dict]:
    ldp = LdpV13().analyze(candles)
    wiki = WikiProV21().scan(candles)
    steps = LdpEngine().run(candles)
    rows = []
    for k, c in enumerate(candles):
        utc, brt = fmt_time(c.ts)
        s_ldp, s_wiki, step = ldp.signals[k], wiki[k], steps[k]
        rows.append(
            {
                "utc": utc,
                "brasilia": brt,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "classe": step.info.cls.value,
                "estruturas": " ".join(sorted({s.name for s in step.structures})),
                "linha_verde": _fmt(ldp.buy_line[k]),
                "linha_vermelha": _fmt(ldp.sell_line[k]),
                "ldp_v13": f"{s_ldp.direction.value}:{s_ldp.setup}" if s_ldp else "",
                "wiki_pro_v21": f"{s_wiki.direction.value}:{s_wiki.details['score']}" if s_wiki else "",
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Relatório de sinais sobre um CSV de velas")
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    candles = read_candles_csv(args.csv)
    rows = build_rows(candles)
    out = args.out or args.csv.with_name(args.csv.stem + "_sinais.csv")
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["utc"])
        writer.writeheader()
        writer.writerows(rows)

    sinais = [r for r in rows if r["ldp_v13"] or r["wiki_pro_v21"]]
    print(f"{len(candles)} velas analisadas, {len(sinais)} com sinal. Relatório completo: {out}")
    print(f"{'Brasília':<17} {'LDP v1.3':<22} {'WIKI PRO V2.1':<14} classe")
    for r in sinais[-30:]:
        print(f"{r['brasilia']:<17} {r['ldp_v13']:<22} {r['wiki_pro_v21']:<14} {r['classe']}")


if __name__ == "__main__":
    main()
