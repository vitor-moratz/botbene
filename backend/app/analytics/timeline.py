"""Períodos (Hoje / 7 dias / Mês / Geral) no horário de Brasília e a linha do tempo de resultados."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.paper import DRAW, LOSS, WIN

BRT = ZoneInfo("America/Sao_Paulo")
PERIODS = ("hoje", "7d", "mes", "geral")
GRANULARITY = {"hoje": "hora", "7d": "dia", "mes": "dia", "geral": "mes"}


def now_brt() -> datetime:
    return datetime.now(BRT)


def period_start(period: str, now: datetime | None = None) -> int | None:
    """Início do período (epoch). None = desde sempre."""
    now = (now or now_brt()).astimezone(BRT)
    day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "hoje":
        return int(day0.timestamp())
    if period == "7d":
        return int((day0 - timedelta(days=6)).timestamp())
    if period == "mes":
        return int(day0.replace(day=1).timestamp())
    return None


def _bucket_start(ts: int, granularity: str) -> datetime:
    dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(BRT)
    if granularity == "hora":
        return dt.replace(minute=0, second=0, microsecond=0)
    if granularity == "dia":
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _next(dt: datetime, granularity: str) -> datetime:
    if granularity == "hora":
        return dt + timedelta(hours=1)
    if granularity == "dia":
        return (dt + timedelta(days=1, hours=2)).replace(hour=0)
    return (dt.replace(day=28) + timedelta(days=4)).replace(day=1)


def _label(dt: datetime, granularity: str) -> str:
    if granularity == "hora":
        return dt.strftime("%Hh")
    if granularity == "dia":
        return dt.strftime("%d/%m")
    return dt.strftime("%m/%Y")


def timeline(rows: Iterable[dict], period: str, now: datetime | None = None) -> list[dict]:
    """Resultado por hora (hoje), por dia (7 dias, mês) ou por mês (geral), sem buracos no eixo."""
    granularity = GRANULARITY.get(period, "dia")
    now = (now or now_brt()).astimezone(BRT)
    rows = list(rows)
    buckets: dict[datetime, dict] = {}
    for r in rows:
        start = _bucket_start(r["entry_ts"], granularity)
        b = buckets.setdefault(start, {"wins": 0, "losses": 0, "draws": 0, "profit": 0.0})
        if r["result"] == WIN:
            b["wins"] += 1
        elif r["result"] == LOSS:
            b["losses"] += 1
        elif r["result"] == DRAW:
            b["draws"] += 1
        b["profit"] += r.get("profit") or 0.0

    since = period_start(period, now)
    if since is not None:
        first = _bucket_start(since, granularity)
    elif buckets:
        first = min(buckets)
    else:
        return []
    last = _bucket_start(int(now.timestamp()), granularity)
    if buckets:
        last = max(last, max(buckets))

    out = []
    cur = first
    while cur <= last and len(out) < 400:
        b = buckets.get(cur, {"wins": 0, "losses": 0, "draws": 0, "profit": 0.0})
        n = b["wins"] + b["losses"]
        out.append({
            "ts": int(cur.timestamp()),
            "label": _label(cur, granularity),
            "n": n,
            "wins": b["wins"],
            "losses": b["losses"],
            "draws": b["draws"],
            "profit": round(b["profit"], 4),
            "winrate": b["wins"] / n if n else None,
        })
        cur = _next(cur, granularity)
    return out


def cumulative(rows: Iterable[dict]) -> list[dict]:
    """Saldo acumulado em entradas, um ponto por vela de entrada (somando scripts na mesma vela)."""
    per_ts: dict[int, float] = {}
    for r in rows:
        per_ts[r["entry_ts"]] = per_ts.get(r["entry_ts"], 0.0) + (r.get("profit") or 0.0)
    total = 0.0
    out = []
    for ts in sorted(per_ts):
        total += per_ts[ts]
        out.append({"time": ts, "value": round(total, 4)})
    return out
