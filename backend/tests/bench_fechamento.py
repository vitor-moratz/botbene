"""Medição da latência das entradas (docs/latencia.md). Não é teste: o pytest não coleta este arquivo.

Uso, de dentro de backend/:
    .venv/bin/python -m tests.bench_fechamento            # dados ao vivo + bancada do fechamento + DeepLOB
    .venv/bin/python -m tests.bench_fechamento --perfil   # idem, com o perfil das funções mais caras

Só lê o banco do bot (data/botbene.sqlite, somente leitura) e a config (pares e estratégias). A bancada roda
o bot com uma corretora falsa e um banco temporário: não conecta na IQ e não encosta no servidor.
"""

from __future__ import annotations

import cProfile
import json
import math
import pstats
import sqlite3
import sys
import tempfile
import time
import timeit
from collections import defaultdict
from pathlib import Path

from app.config import Settings
from app.db.database import Database
from app.market.candle import Candle
from app.service.bot import BotService
from app.service.events import EventHub
from app.service.orders import OrderManager
from tests.fakes import FakeBroker

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
LIVE = 40  # fechamentos medidos na bancada
GALE_STRATS = ("bb_rci", "retracao_comando")  # as que operam com gale em 09/11/2026


def _q(xs: list[float]) -> str:
    xs = sorted(xs)
    n = len(xs)
    if not n:
        return "n=0"
    return f"n={n} mediana={xs[n // 2]:.2f} p90={xs[int(n * .9)]:.2f} máx={xs[-1]:.2f}"


def live_data(db_path: Path) -> None:
    """O que as entradas reais mostram: segundo do toque por estratégia, espera do gale e acerto na hora × atrasada."""
    c = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    print("== Dados ao vivo (últimos 3 dias) ==")
    print("Segundo da vela em que o bot viu o toque (relógio da IQ). Em bb_rci e deeplob_iq o gatilho é o 1º preço:")
    rows = c.execute("""select strategy, json_extract(details,'$.touch.sec') from signals
        where origin='ao_vivo' and json_extract(details,'$.touch.sec') is not null and entry_ts > strftime('%s','now')-3*86400""").fetchall()
    by: dict[str, list[float]] = defaultdict(list)
    for strat, sec in rows:
        by[strat].append(sec)
    for strat, xs in sorted(by.items()):
        print(f"  {strat:22s} {_q(xs)}")
    marks = ",".join("?" * len(GALE_STRATS))
    rows = c.execute(f"""select o.requested_at - s.entry_ts, o.status, json_extract(s.details,'$.corretora.velas')
        from orders o join signals s on s.id=o.signal_id
        where o.strategy in ({marks}) and o.status in ('win','loss') and json_extract(s.details,'$.touch.sec') is not null""",
                     GALE_STRATS).fetchall()
    late = [r for r in rows if r[0] >= 3]
    print(f"\nOrdens de {', '.join(GALE_STRATS)}: {len(late)} de {len(rows)} saíram com 3 s ou mais de vela (espera do gale)")
    for name, rs in (("na hora (<3 s)", [r for r in rows if r[0] < 3]), ("atrasadas (>=3 s)", late)):
        n = len(rs)
        if not n:
            continue
        p = sum(1 for r in rs if r[1] == "win") / n
        print(f"  {name:18s} {n:4d} ordens, acerto {p:.0%} (±{1.96 * math.sqrt(p * (1 - p) / n):.0%})")


class MultiFake(FakeBroker):
    """Uma série de velas por par, todas no mesmo relógio, que o teste avança."""

    def __init__(self, series: dict[str, list[Candle]]):
        super().__init__(next(iter(series.values()))[:-LIVE], [])
        self.hist = {a: s[:-LIVE] for a, s in series.items()}
        self.stream = {a: s[-LIVE:] for a, s in series.items()}
        self.step = -1
        self.clock = 0.0

    def get_candles(self, asset, timeframe, count, end_ts=None):
        return self.hist[asset][-count:] if timeframe == 60 else []

    def stream_candles(self, asset, timeframe):
        return [self.stream[asset][self.step]] if self.step >= 0 else []

    def server_time(self):
        return self.clock

    def tradable(self, asset, kind="binary"):
        return (True, "ok") if kind == "binary" else (False, "sem digital")

    def payout_now(self, asset, kind="binary"):
        return 0.83 if kind == "binary" else None


def bench_close(db_path: Path, profile: bool) -> None:
    """O "estouro" do segundo 0: todos os pares fecham a vela na mesma volta do bot."""
    cfg = json.loads((DATA / "config.json").read_text())
    c = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    series = {}
    for asset in cfg["assets"]:
        rows = c.execute("select ts, open, high, low, close from candles where asset=? and timeframe=60 order by ts desc limit 1500",
                         (asset,)).fetchall()
        if len(rows) > 600:
            series[asset] = [Candle(*r) for r in reversed(rows)]
    common = sorted(set.intersection(*(set(x.ts for x in s) for s in series.values())))[-LIVE:]
    series = {a: [x for x in s if x.ts <= common[-1]] for a, s in series.items()}
    series = {a: s for a, s in series.items() if [x.ts for x in s[-LIVE:]] == common}
    print(f"\n== Bancada do fechamento: {len(series)} pares, {LIVE} velas, estratégias da config ==")

    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(_env_file=None, data_dir=Path(tmp), history_candles=1400)
        db = Database(settings.db_url())
        broker = MultiFake(series)
        broker.clock = common[0] - 59.0
        hub = EventHub()
        orders = OrderManager(db, hub, lambda: broker, sleep=lambda s: None, now=broker.server_time, threaded=False)
        bot = BotService(settings, db, hub, lambda: broker, orders=orders, strategies_factory=list)
        bot.config.update({"strategies": cfg["strategies"]})
        bot.configure(list(series), 60)
        t0 = time.perf_counter()
        bot._bootstrap(broker, full_day=False)
        print(f"carga dos pares: {time.perf_counter() - t0:.1f} s")
        bot.mode = "automatico_veto"

        timings: dict[str, list[float]] = defaultdict(list)

        def wrap(obj, name, label):
            fn = getattr(obj, name)

            def timed(*a, **k):
                t = time.perf_counter()
                try:
                    return fn(*a, **k)
                finally:
                    timings[label].append(time.perf_counter() - t)
            setattr(obj, name, timed)

        wrap(bot, "_on_close", "_on_close (tudo, por par)")
        wrap(bot, "snapshot", "snapshot (status do painel)")
        wrap(db, "save_candles", "db.save_candles")
        wrap(bot, "_resolve_pending", "_resolve_pending (banco)")
        wrap(bot, "_open_approvals", "_open_approvals")
        for r in bot.runners.values():
            wrap(r.engine, "process", "engine.process (leitura LdP)")
            for s in r.intra:
                wrap(s, "on_step", f"on_step {s.name}")

        prof = cProfile.Profile() if profile else None
        bursts = []
        for i in range(LIVE):
            broker.step, broker.clock = i, common[i] + 1.0
            t = time.perf_counter()
            if prof:
                prof.enable()
            bot._poll(broker)
            if prof:
                prof.disable()
            bursts.append(time.perf_counter() - t)
        bursts = sorted(bursts[1:])  # a 1ª volta só abre a vela
        n = len(bursts)
        print(f"volta do fechamento (todos os pares): mediana {bursts[n // 2] * 1000:.0f} ms, "
              f"p90 {bursts[int(n * .9)] * 1000:.0f} ms, máx {bursts[-1] * 1000:.0f} ms")
        print("por etapa, em ms (mediana por chamada / p90 por chamada / soma por volta):")
        for label, xs in sorted(timings.items(), key=lambda kv: -sum(kv[1])):
            ys = sorted(xs)
            print(f"  {label:36s} {ys[len(ys) // 2] * 1000:7.2f} / {ys[int(len(ys) * .9)] * 1000:7.2f} / {sum(xs) / n * 1000:7.1f}")
        if prof:
            pstats.Stats(prof).sort_stats("cumulative").print_stats(30)


def bench_misc() -> None:
    import threading

    import numpy as np

    from app.strategies import deeplob_net as net
    from app.strategies.deeplob import MODEL

    print("\n== Peças soltas ==")
    p = net.load(MODEL)
    rng = np.random.default_rng(1)
    closes = 1.1 + np.cumsum(rng.normal(0, 1e-5, 101))
    bars = [(1794259000 + 5 * i, x, x + 1e-5, x - 1e-5, x) for i, x in enumerate(closes)]
    net.probability(p, net.window_features(bars))
    n = 100
    t = timeit.timeit(lambda: net.probability(p, net.window_features(bars)), number=n) / n
    print(f"DeepLOB (numpy), uma previsão: {t * 1000:.2f} ms")

    def one():
        th = threading.Thread(target=lambda: None)
        th.start()
        th.join()
    n = 2000
    t = timeit.timeit(one, number=n) / n
    print(f"abrir e esperar uma thread (cada leitura da IQ passa por call_with_deadline): {t * 1e6:.0f} µs")


def main() -> None:
    db_path = DATA / "botbene.sqlite"
    live_data(db_path)
    bench_close(db_path, profile="--perfil" in sys.argv)
    bench_misc()


if __name__ == "__main__":
    main()
