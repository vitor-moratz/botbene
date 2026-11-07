"""Validação do Score LDP v1 em dados que ele nunca viu.

A regra foi congelada em 06/11/2026 (docs/estrategia.md, seção 2d). Só vale como prova o que acontece DEPOIS disso:
por padrão, entradas a partir de 07/11/2026 00:00 (Brasília). O OTC tem dados no fim de semana; os pares -op
voltam na segunda, 09/11. O arquivo automático do bot guarda as velas de 5 s dos pares configurados e dos 12 -op
da pesquisa a cada 6 h, enquanto o servidor estiver ligado (a IQ só mantém 5 s por ~1 semana).

Uso (dentro de backend/, com o venv ativo):
    python -m app.tools.score_check
    python -m app.tools.score_check --desde 2026-11-09 --payout 0.84
    python -m app.tools.score_check --pares EURUSD-op,GBPUSD-op

Mede com a mesma classe que o bot roda (app/strategies/score.py), nas velas de 5 s guardadas, e também mostra o placar
ao vivo das ordens do score no banco do bot. Para melhorar o score: escreva uma versão nova com outro nome, congele as
regras ANTES de medir e compare as duas aqui, só em dados posteriores ao congelamento da nova.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import datetime

from app.analytics.stats import breakeven, wilson
from app.analytics.timeline import BRT
from app.analytics.validation import needed_winrate
from app.config import get_settings
from app.db.database import Database
from app.market.candle import is_otc
from app.research.dataset import SUB_TF, load, research_db
from app.research.evaluate import intra_entries
from app.strategies.score import NAME, PATTERN_LABELS, PATTERNS, ScoreLdp

FROZEN_FROM = "2026-11-07"
TARGET = 0.65  # meta do dono do bot
WARMUP = 6 * 3600  # velas de 1 min antes da primeira de 5 s, para a leitura e as médias já chegarem prontas


def verdict(n: int, wins: int, be: float) -> str:
    if n < 30:
        return "começando: menos de 30 entradas ainda oscila demais"
    lo, hi = wilson(wins, n)
    parts = []
    if lo > be:
        parts.append("ACIMA DO EMPATE, comprovado")
    elif hi < be:
        parts.append("ABAIXO DO EMPATE")
    else:
        need = needed_winrate(n, be)
        parts.append("ainda no empate" + (f" (com {n} entradas, provaria a partir de {100 * need:.1f}%)" if need else ""))
    if lo >= TARGET:
        parts.append("meta de 65% comprovada")
    elif hi >= TARGET:
        parts.append("65% ainda possível")
    else:
        parts.append("65% fora da faixa")
    return " · ".join(parts)


def line(label: str, rows: list[dict], be: float, days: float | None = None) -> str:
    n = sum(r["result"] in ("win", "loss") for r in rows)
    wins = sum(r["result"] == "win" for r in rows)
    if not n:
        return f"{label:46s} sem entradas"
    lo, hi = wilson(wins, n)
    per_day = f" · {n / days:5.1f}/dia" if days else ""
    return (f"{label:46s} {wins:4d}/{n:<4d} = {100 * wins / n:5.1f}%  (faixa {100 * lo:4.1f}–{100 * hi:4.1f}%){per_day}  "
            f"→ {verdict(n, wins, be)}")


def research_rows(since: int, assets: list[str] | None, payout: float) -> tuple[list[dict], dict[str, tuple[int, int]]]:
    db = research_db(get_settings())
    series = {s["asset"]: s for s in db.candle_series() if s["timeframe"] == SUB_TF and s["last_ts"] >= since}
    names = [a for a in (assets or sorted(series)) if a in series]
    rows, span = [], {}
    for asset in names:
        m1, subs = load(db, asset, 60), load(db, asset, SUB_TF)
        if not subs:
            continue
        m1 = [c for c in m1 if c.ts >= subs[0].ts - WARMUP]
        for e in intra_entries(asset, m1, subs, payout, [ScoreLdp()]):
            if e["entry_ts"] >= since:
                rows.append(e)
        span[asset] = (max(since, subs[0].ts), subs[-1].ts)
        print(f"  {asset}: medido até {datetime.fromtimestamp(subs[-1].ts, BRT):%d/%m %H:%M}", file=sys.stderr, flush=True)
    return rows, span


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--desde", default=FROZEN_FROM, help="AAAA-MM-DD (Brasília); padrão: o dia seguinte ao congelamento")
    ap.add_argument("--pares", default="", help="lista separada por vírgula; padrão: todos com velas de 5 s")
    ap.add_argument("--payout", type=float, default=0.84)
    args = ap.parse_args(argv)
    since = int(datetime.strptime(args.desde, "%Y-%m-%d").replace(tzinfo=BRT).timestamp())
    be = breakeven(args.payout)
    print(f"Score LDP v1 · entradas desde {args.desde} · payout {100 * args.payout:.0f}% · empate {100 * be:.1f}% · meta {100 * TARGET:.0f}%")

    rows, span = research_rows(since, [a for a in args.pares.split(",") if a] or None, args.payout)
    days = {a: (end - start) / 86400 for a, (start, end) in span.items()}
    print("\nPESQUISA (velas de 5 s guardadas, mesma classe do bot)")
    groups = (("todos", lambda r: True), ("pares -op", lambda r: not is_otc(r["asset"])), ("pares OTC", lambda r: is_otc(r["asset"])))
    for label, keep in groups:
        sel = [r for r in rows if keep(r)]
        d = max((v for a, v in days.items() if keep({"asset": a})), default=0) or None
        print(line(label, sel, be, d))
    print("\nPor dia")
    by_day = defaultdict(list)
    for r in rows:
        by_day[datetime.fromtimestamp(r["entry_ts"], BRT).strftime("%d/%m")].append(r)
    for d in sorted(by_day, key=lambda s: (s[3:], s[:2])):
        print(line(d, by_day[d], be))
    print("\nPor quantidade de padrões")
    for k in (3, 4):
        print(line(f"{k} de 4", [r for r in rows if r["score"] == k], be))
    print("\nCada padrão (entre as entradas)")
    for k in PATTERNS:
        print(line(f"com {PATTERN_LABELS[k]}", [r for r in rows if r["confluences"].get(k)], be))
    print("\nPor par")
    for a in sorted({r["asset"] for r in rows}):
        print(line(a, [r for r in rows if r["asset"] == a], be))

    settings = get_settings()
    live = Database(settings.db_url()).list_signals(limit=100_000, strategy=NAME, origin="ao_vivo", since_ts=since - 60)
    print("\nAO VIVO (sinais do bot, conta demo ou real, o que estiver configurado)")
    print(line("ao vivo", live, be))


if __name__ == "__main__":
    main()
