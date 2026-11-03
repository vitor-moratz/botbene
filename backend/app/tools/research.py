"""Base de pesquisa: baixa velas de vários ativos e mede as estratégias nelas.

Uso (dentro de backend/, com o venv ativo):
    python -m app.tools.research baixar --dias 8
    python -m app.tools.research baixar --dias 8 --ativos EURUSD,GBPUSD
    python -m app.tools.research baixar --dias 60 --tempos 60      # só velas de 1 min, mais longe
    python -m app.tools.research relatorio
    python -m app.tools.research relatorio --ajuste 0.6   # 60% iniciais para ajustar, resto para conferir

O bot opera em velas de 1 min; as de 5 s servem só para saber o que aconteceu DENTRO de cada
minuto (o gatilho de 15 s da apostila).
"""

from __future__ import annotations

import argparse
import logging

from app.analytics.stats import breakeven
from app.config import get_settings
from app.research.dataset import DEFAULT_ASSETS, SUB_TF, download, load, research_db
from app.research.evaluate import close_entries, headline, intra_entries, split_ts, table
from app.strategies import STRATEGY_LABELS
from app.strategies.intra import INTRA_NAMES
from app.tools.common import fmt_time, make_broker, setup_logging

log = logging.getLogger(__name__)


def cmd_baixar(args: argparse.Namespace) -> None:
    db = research_db(get_settings())
    broker = make_broker()
    now = int(broker.server_time())
    since = now - args.dias * 86400

    def progress(asset: str, tf: int, n: int, oldest: int) -> None:
        if n % 10_000 < 1000:
            print(f"  {asset} {tf:>2d}s: {n} velas, até {fmt_time(oldest)[1]}", flush=True)

    for asset in args.ativos.split(","):
        for tf in (int(x) for x in args.tempos.split(",")):
            try:
                n = download(broker, db, asset, tf, since, now, progress)
                print(f"{asset} {tf}s: {n} velas", flush=True)
            except Exception as exc:  # noqa: BLE001 - um ativo com problema não para os outros
                print(f"{asset} {tf}s: falhou ({exc})", flush=True)
    for s in db.candle_series():
        print(f"  {s['asset']:10s} {s['timeframe']:>2d}s {s['count']:7d} velas  {fmt_time(s['first_ts'])[1]} .. {fmt_time(s['last_ts'])[1]}")


def cmd_relatorio(args: argparse.Namespace) -> None:
    db = research_db(get_settings())
    series = db.candle_series()
    assets = sorted({s["asset"] for s in series if s["timeframe"] == 60})
    if args.ativos:
        assets = [a for a in assets if a in args.ativos.split(",")]
    entries: list[dict] = []
    for asset in assets:
        m1, subs = load(db, asset, 60), load(db, asset, SUB_TF)
        if subs:
            m1 = [c for c in m1 if c.ts >= subs[0].ts - 600]  # mesmo período para todos os scripts
        entries += close_entries(asset, m1, args.payout)
        entries += intra_entries(asset, m1, subs, args.payout)
        print(f"{asset}: {len(m1)} velas de 1 min, {len(subs)} de 5 s", flush=True)

    cut = split_ts(entries, args.ajuste)
    parts = {"ajuste": [e for e in entries if e["entry_ts"] < cut], "conferência": [e for e in entries if e["entry_ts"] >= cut]}
    print(f"\nMínimo para empatar com payout {args.payout:.0%}: {breakeven(args.payout) * 100:.1f}%")
    print(f"Ajuste até {fmt_time(cut)[1]}; conferência depois.\n")
    label = lambda e: STRATEGY_LABELS.get(e["strategy"], e["strategy"])  # noqa: E731
    for name, part in parts.items():
        print(f"== {name} ==")
        print(headline(part))
        for line in table(part, label):
            print("  " + line)
    for name in INTRA_NAMES:
        rows = [e for e in entries if e["strategy"] == name]
        if not rows:
            continue
        print(f"\n== {STRATEGY_LABELS[name]}: detalhes (período todo) ==")
        breakdown = [("ativo", lambda e: e["asset"]), ("dia", lambda e: fmt_time(e["entry_ts"])[1][:10]),
                     ("hora (Brasília)", lambda e: f"{e['hour']:02d}h")]
        if name == "ldp_apostila":
            breakdown += [("gatilho", lambda e: e["trigger"]), ("marcação", lambda e: e["source"].split(":")[0]),
                          ("confluências", lambda e: f"{e['score']} pontos")]
        for title, key in breakdown:
            print(f"-- por {title}")
            for line in table(rows, key, min_n=args.min_n):
                print("  " + line)


def main() -> None:
    parser = argparse.ArgumentParser(description="Base de pesquisa do BotBene")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("baixar", help="baixa velas de 1 min e 5 s da IQ Option")
    p.add_argument("--dias", type=int, default=8)
    p.add_argument("--ativos", default=",".join(DEFAULT_ASSETS))
    p.add_argument("--tempos", default=f"60,{SUB_TF}", help="tempos de vela em segundos (5 s só existe ~1 semana para trás)")
    p.set_defaults(func=cmd_baixar)
    r = sub.add_parser("relatorio", help="mede as estratégias na base baixada")
    r.add_argument("--ativos", default="")
    r.add_argument("--payout", type=float, default=0.85)
    r.add_argument("--ajuste", type=float, default=0.6, help="fração inicial usada para ajustar")
    r.add_argument("--min-n", type=int, default=10)
    r.set_defaults(func=cmd_relatorio)
    args = parser.parse_args()
    setup_logging()
    logging.getLogger("iqoptionapi").setLevel(logging.WARNING)
    args.func(args)


if __name__ == "__main__":
    main()
