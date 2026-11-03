"""Baixa velas fechadas da IQ Option e salva em CSV.

Uso (dentro de backend/, com o venv ativo):
    python -m app.tools.fetch_candles --asset EURUSD --tf 60 --count 2000
    python -m app.tools.fetch_candles --asset EURUSD-OTC --tf 60 --count 2000
"""

from __future__ import annotations

import argparse
from pathlib import Path

from app.config import get_settings
from app.market.csvio import write_candles_csv
from app.tools.common import fmt_time, make_broker, setup_logging


def main() -> None:
    parser = argparse.ArgumentParser(description="Baixa velas da IQ Option para CSV")
    parser.add_argument("--asset", default="EURUSD")
    parser.add_argument("--tf", type=int, default=60, help="tamanho da vela em segundos")
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    setup_logging()

    broker = make_broker()
    candles = broker.get_candles(args.asset, args.tf, args.count)
    out = args.out or get_settings().resolved_data_dir() / "candles" / f"{args.asset}_{args.tf}.csv"
    write_candles_csv(out, candles)
    if candles:
        first, last = fmt_time(candles[0].ts)[1], fmt_time(candles[-1].ts)[1]
        print(f"{len(candles)} velas salvas em {out} ({first} até {last}, horário de Brasília)")
    else:
        print("Nenhuma vela recebida. O ativo está aberto neste horário?")


if __name__ == "__main__":
    main()
