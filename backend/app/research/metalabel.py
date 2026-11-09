"""Meta-labeling da retração no comando: o conjunto de dados para um modelo que decide PEGAR ou PULAR cada entrada.

A estratégia (v1, que contém a v2) continua decidindo a direção. Aqui só se monta, para cada entrada que ela fez, a lista
fixa de variáveis conhecidas NO MOMENTO DO TOQUE e o resultado. Regras do estudo em docs/metalabel_preregistro.md.

Princípio: `features()` é a única função de variáveis. O replay das velas de 5 s (este módulo) e, depois, o bot ao vivo
usam a mesma, para o modelo nunca ver no treino algo diferente do que verá operando.
"""

from __future__ import annotations

import math
from bisect import bisect_left
from collections import defaultdict, deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.db.database import Database
from app.ldp.engine import LdpEngine
from app.market.candle import Candle, is_otc
from app.paper import judge
from app.strategies.base import Direction
from app.strategies.ldp_apostila import ArmedSetup, touch_bar
from app.strategies.retracao_comando import RetracaoComando, RetracaoComandoV2

BRT = timezone(timedelta(hours=-3))
SUB = 5
ATR_PERIOD = 14
DAY = 1440  # velas M1 para o ATR "do dia" (regime de volatilidade)
RECENT = 20  # entradas anteriores para o acerto recente
NAN = float("nan")

# Ordem fixa (pré-registrada). Mudar a lista = estudo novo.
FEATURES = (
    "cmd_range_atr", "cmd_body_ratio", "cmd_wick_fav", "cmd_wick_back", "run_length",
    "brk10_atr", "brk10", "atr_rel", "ema_slope_fav", "prev_range_atr", "prev_same",
    "touch_sec", "gap_fav_atr", "run_fav_atr", "depth_extra_atr", "price_vs_open_atr",
    "hour_sin", "hour_cos", "weekday", "otc",
    "mood_side", "mood_chg_fav", "mood_age",
    "recent_wr",
)


@dataclass(frozen=True)
class TouchSnapshot:
    """A vela de entrada até o instante do toque, e o sentimento naquele instante (fração ACIMA, como a IQ manda)."""

    open: float
    high: float
    low: float
    price: float  # preço da entrada
    sec: float  # segundos desde a abertura da vela de entrada
    mood: float | None = None
    mood_age: float | None = None
    mood_60s: float | None = None  # fração ACIMA 60 s antes do toque


def snapshot_from_bars(setup: ArmedSetup, bars: Sequence[Candle], mood: Callable[[int], tuple[float, float] | None] | None = None) -> TouchSnapshot:
    """Snapshot pelas velas de 5 s da janela até a do toque (inclusive). O preço é o fechamento da vela do toque, como no
    backtest, e o instante é o fim dela (quando esse preço existe). `mood(ts)` devolve (valor, idade) gravados em ts."""
    t = bars[-1].ts + SUB
    now = mood(t - t % SUB) if mood else None
    before = mood(t - t % SUB - 60) if mood else None
    return TouchSnapshot(open=bars[0].open, high=max(b.high for b in bars), low=min(b.low for b in bars),
                         price=bars[-1].close, sec=float(t - setup.target_ts),
                         mood=now[0] if now else None, mood_age=now[1] if now else None,
                         mood_60s=before[0] if before else None)


def _ema(values: Sequence[float], period: int) -> list[float]:
    a, out = 2 / (period + 1), []
    for v in values:
        out.append(v if not out else a * v + (1 - a) * out[-1])
    return out


def features(setup: ArmedSetup, closed: Sequence[Candle], snap: TouchSnapshot, run_length: int,
             otc: bool, recent_wr: float = NAN) -> dict[str, float]:
    """Variáveis da entrada, só com o que se sabe no toque. `closed` = velas M1 fechadas até a vela de comando (a última)."""
    k = closed[-1]
    d = 1 if setup.direction is Direction.CALL else -1
    before = closed[-ATR_PERIOD - 1:-1]
    atr = sum(c.high - c.low for c in before) / len(before) if before else NAN
    rng = k.high - k.low
    if not atr or atr <= 0 or rng <= 0:
        return {f: NAN for f in FEATURES}
    day = closed[-DAY - 1:-1]
    atr_day = sum(c.high - c.low for c in day) / len(day) if len(day) >= 120 else NAN
    top, bottom = max(k.open, k.close), min(k.open, k.close)
    wick_up, wick_dn = (k.high - top) / rng, (bottom - k.low) / rng
    ten = closed[-11:-1]
    if ten:
        edge = max(c.high for c in ten) if d > 0 else min(c.low for c in ten)
        brk = d * (k.close - edge) / atr
    else:
        brk = NAN
    closes = [c.close for c in closed[-60:]]
    ema = _ema(closes, 21)
    slope = d * (ema[-1] - ema[-6]) / atr if len(ema) >= 6 else NAN
    prev = closed[-2] if len(closed) >= 2 else None
    prev_body = (prev.close - prev.open) if prev else 0.0
    hour = datetime.fromtimestamp(setup.target_ts, BRT)
    h = hour.hour + hour.minute / 60
    side = (snap.mood if d > 0 else 1 - snap.mood) if snap.mood is not None else NAN
    chg = d * (snap.mood - snap.mood_60s) if snap.mood is not None and snap.mood_60s is not None else NAN
    return {
        "cmd_range_atr": rng / atr,
        "cmd_body_ratio": abs(k.close - k.open) / rng,
        "cmd_wick_fav": wick_up if d > 0 else wick_dn,  # pavio na ponta do movimento (rejeição)
        "cmd_wick_back": wick_dn if d > 0 else wick_up,
        "run_length": float(run_length),
        "brk10_atr": brk,
        "brk10": float(brk > 0) if brk == brk else NAN,
        "atr_rel": atr / atr_day if atr_day == atr_day and atr_day > 0 else NAN,
        "ema_slope_fav": slope,
        "prev_range_atr": (prev.high - prev.low) / atr if prev else NAN,
        "prev_same": float((prev_body > 0) - (prev_body < 0)) * d if prev else NAN,
        "touch_sec": snap.sec,
        "gap_fav_atr": d * (snap.open - k.close) / atr,
        "run_fav_atr": ((snap.high - snap.open) if d > 0 else (snap.open - snap.low)) / atr,
        "depth_extra_atr": ((snap.open - snap.low) if d > 0 else (snap.high - snap.open)) / atr - 0.8,
        "price_vs_open_atr": d * (snap.price - snap.open) / atr,
        "hour_sin": math.sin(2 * math.pi * h / 24),
        "hour_cos": math.cos(2 * math.pi * h / 24),
        "weekday": float(hour.weekday()),
        "otc": float(otc),
        "mood_side": side,
        "mood_chg_fav": chg,
        "mood_age": snap.mood_age if snap.mood_age is not None else NAN,
        "recent_wr": recent_wr,
    }


# ---------------------------------------------------------------------- conjunto de dados (replay)


def _mood_lookup(db: Database, asset: str) -> Callable[[int], tuple[float, float] | None]:
    rows = {ts: (v, age) for ts, v, age in db.load_mood(asset)}
    return rows.get


def entries_for_asset(asset: str, m1: Sequence[Candle], subs: Sequence[Candle],
                      mood: Callable[[int], tuple[float, float] | None] | None = None, timeframe: int = 60) -> list[dict]:
    """Entradas da retração no comando v1 num par (com a marca de quais a v2 também faria), com variáveis e rótulos."""
    subs = sorted(subs, key=lambda s: s.ts)
    keys = [s.ts for s in subs]
    v1, v2 = RetracaoComando(timeframe=timeframe), RetracaoComandoV2(timeframe=timeframe)
    engine = LdpEngine()
    out = []
    for i, c in enumerate(m1):
        step = engine.process(c)
        plan = v1.on_step(step, engine)
        if not plan.armed or i + 1 >= len(m1):
            continue
        in_v2 = bool(v2.on_step(step, engine).armed)
        nxt = m1[i + 1]
        if nxt.ts != c.ts + timeframe:
            continue
        inside = subs[bisect_left(keys, nxt.ts):bisect_left(keys, nxt.ts + timeframe)]
        if not inside:
            continue
        setup = plan.armed[0]
        bar, bars, _ = touch_bar(setup, inside)
        if bar is None:
            continue
        snap = snapshot_from_bars(setup, bars, mood)
        f = features(setup, engine.candles, snap, step.run_length, is_otc(asset))
        result = judge(setup.direction.value, bar.close, nxt.close)
        later = [s for s in inside if s.ts > bar.ts]
        result_5s = judge(setup.direction.value, later[0].close, nxt.close) if later else None
        out.append({"asset": asset, "market": "OTC" if is_otc(asset) else "op", "decision_ts": setup.decision_ts,
                    "entry_ts": setup.target_ts, "touch_ts": setup.target_ts + int(snap.sec), "direction": setup.direction.value,
                    "is_v2": int(in_v2), "entry_price": bar.close, "exit_price": nxt.close, "result": result,
                    "result_5s": result_5s, **f})
    return out


def add_recent_wr(rows: list[dict], timeframe: int = 60) -> None:
    """Acerto das últimas RECENT entradas do mesmo mercado que já tinham vencido no instante do toque (sem olhar o futuro)."""
    by_market: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_market[r["market"]].append(r)
    for market_rows in by_market.values():
        market_rows.sort(key=lambda r: r["touch_ts"])
        done = sorted((r for r in market_rows if r["result"] in ("win", "loss")), key=lambda r: r["entry_ts"] + timeframe)
        window: deque[int] = deque(maxlen=RECENT)
        j = 0
        for r in market_rows:
            while j < len(done) and done[j]["entry_ts"] + timeframe <= r["touch_ts"]:
                window.append(int(done[j]["result"] == "win"))
                j += 1
            r["recent_wr"] = sum(window) / len(window) if len(window) >= 5 else NAN


def build_dataset(db: Database, assets: Sequence[str], timeframe: int = 60,
                  progress: Callable[[str, int], None] | None = None) -> list[dict]:
    """Replay em toda a base de pesquisa (velas M1 + 5 s + sentimento gravados)."""
    rows: list[dict] = []
    for asset in assets:
        subs = db.load_candles(asset, SUB, 10_000_000)
        if not subs:
            continue
        m1 = [c for c in db.load_candles(asset, timeframe, 10_000_000) if c.ts >= subs[0].ts - (DAY + 60) * 60]
        found = entries_for_asset(asset, m1, subs, _mood_lookup(db, asset), timeframe)
        rows.extend(found)
        if progress:
            progress(asset, len(found))
    add_recent_wr(rows, timeframe)
    rows.sort(key=lambda r: (r["entry_ts"], r["asset"]))
    return rows
