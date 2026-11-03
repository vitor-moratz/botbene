"""Acompanha um ativo ao vivo e mostra, a cada vela fechada, a leitura da apostila e os
sinais dos scripts portados. NÃO envia ordens.

Uso:
    python -m app.tools.live_watch --asset EURUSD --tf 60
Pare com Ctrl+C.
"""

from __future__ import annotations

import argparse
import time

from app.broker.base import BrokerError
from app.ldp.engine import LdpEngine
from app.market.candle import Candle
from app.market.store import CandleStore
from app.strategies.ldp_v13 import LdpV13
from app.strategies.wiki_pro_v21 import WikiProV21
from app.tools.common import fmt_time, make_broker, setup_logging

STREAM_GRACE_SECONDS = 3


def main() -> None:
    parser = argparse.ArgumentParser(description="Leitura ao vivo, sem ordens")
    parser.add_argument("--asset", default="EURUSD")
    parser.add_argument("--tf", type=int, default=60)
    parser.add_argument("--history", type=int, default=500)
    args = parser.parse_args()
    setup_logging()

    broker = make_broker()
    store = CandleStore(args.asset, args.tf)
    store.load_history(broker.get_candles(args.asset, args.tf, args.history))
    engine = LdpEngine()
    engine.run(store.closed)
    strategies = [LdpV13(), WikiProV21()]
    print(f"{len(store.closed)} velas de histórico carregadas. Acompanhando {args.asset} M{args.tf // 60 or args.tf}…")

    def on_close(candle: Candle) -> None:
        step = engine.process(candle)
        history = store.closed
        _, brt = fmt_time(candle.ts)
        names = ", ".join(sorted({s.name for s in step.structures})) or "-"
        zone = engine.levels.zone(candle.close)
        sup = f"{zone.support.price:.6f}" if zone.support else "-"
        res = f"{zone.resistance.price:.6f}" if zone.resistance else "-"
        print(f"\n[{brt}] fechou {candle.close:.6f} | {step.info.cls.value} | estruturas: {names}")
        print(f"    suporte {sup} / resistência {res}")
        for strat in strategies:
            sig = strat.evaluate_last(history)
            if sig:
                print(f"    >>> {strat.name}: {sig.direction.value.upper()} ({sig.setup}) para a próxima vela")

    broker.start_stream(args.asset, args.tf)
    try:
        while True:
            for candle in broker.stream_candles(args.asset, args.tf):
                for closed in store.ingest(candle):
                    on_close(closed)
            for closed in store.close_forming_if_expired(broker.server_time() - STREAM_GRACE_SECONDS):
                on_close(closed)
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nEncerrando…")
    finally:
        try:
            broker.stop_stream(args.asset, args.tf)
        except BrokerError:
            pass  # a IQ às vezes não confirma o fim do stream; ao sair do programa ele para de qualquer jeito


if __name__ == "__main__":
    main()
