"""Monta os dados do gráfico do painel: velas, linhas do v1.3, sinais e marcações próximas."""

from __future__ import annotations

from collections.abc import Sequence

from app.ldp.engine import EngineStep, LdpEngine
from app.ldp.levels import Role
from app.ldp.reading import read_candles
from app.market.candle import Candle
from app.strategies import MANUAL
from app.strategies.ldp_v13 import LdpV13
from app.strategies.wiki_pro_v21 import WikiProV21

LEVELS_EACH_SIDE = 3
NOT_SENT = ("bloqueada", "erro")  # ordens que nunca chegaram à corretora: não são entrada


def candle_dict(c: Candle) -> dict:
    return {"time": c.ts, "open": c.open, "high": c.high, "low": c.low, "close": c.close}


def reading(engine: LdpEngine | None, step: EngineStep | None) -> dict | None:
    """Leitura da última vela fechada: classe, estruturas e suporte/resistência mais próximos."""
    if engine is None or step is None:
        return None
    close = step.info.candle.close
    zone = engine.levels.zone(close)

    def lvl(level) -> dict | None:
        if level is None:
            return None
        return {"price": level.price, "strength": level.strength, "sources": level.sources[:4], "distance": abs(level.price - close)}

    return {
        "ts": step.info.candle.ts,
        "close": close,
        "classe": step.info.cls.value,
        "estruturas": [{"name": s.name, "page": s.page, "detail": s.detail} for s in step.structures],
        "support": lvl(zone.support),
        "resistance": lvl(zone.resistance),
        "atr": step.atr,
    }


def nearby_levels(engine: LdpEngine, price: float) -> list[dict]:
    supports = sorted((lv for lv in engine.levels.active(Role.SUPPORT) if lv.price <= price), key=lambda lv: -lv.price)
    resistances = sorted((lv for lv in engine.levels.active(Role.RESISTANCE) if lv.price >= price), key=lambda lv: lv.price)
    out = []
    for lv in supports[:LEVELS_EACH_SIDE] + resistances[:LEVELS_EACH_SIDE]:
        out.append({"price": lv.price, "role": lv.role.value, "strength": lv.strength, "sources": lv.sources[:4]})
    return out


def ldp_overlay(candles: Sequence[Candle], start: int = 0, next_ts: int | None = None) -> dict:
    """O que o script LDP v1.3 desenha: as linhas de 50% e as setas CALL/PUT.

    Só desenho: sai das velas, não grava sinal nem manda ordem. `next_ts` é a vela depois da última
    fechada, que já mostra a linha que vale agora, como no script.
    """
    res = LdpV13().analyze(candles)

    def point(ts: int, value: float | None) -> dict:
        return {"time": ts, "value": value} if value is not None else {"time": ts}

    buy_line, sell_line, marks = [], [], []
    for k in range(start, len(candles)):
        ts = candles[k].ts
        buy_line.append(point(ts, res.buy_line[k]))
        sell_line.append(point(ts, res.sell_line[k]))
        signal = res.signals[k]
        if signal is not None:
            marks.append({"time": ts, "direction": signal.direction.value, "setup": signal.setup})
    if candles and next_ts is not None and next_ts > candles[-1].ts:
        buy, sell = res.lines_after_close(len(candles) - 1, candles)
        buy_line.append(point(next_ts, buy))
        sell_line.append(point(next_ts, sell))
    return {"buy_line": buy_line, "sell_line": sell_line, "script_marks": marks}


def build_reading(asset: str, timeframe: int, candles: Sequence[Candle], limit: int) -> dict:
    """A leitura do estudo para desenhar no gráfico: lotes, regiões, rótulos e cenário. Só leitura."""
    if not candles:
        return {"asset": asset, "timeframe": timeframe, "lots": [], "regions": [], "tags": [], "scenarios": [], "scenario": None}
    _, reading = read_candles(list(candles))
    start = max(0, len(candles) - limit)
    last = len(candles) - 1

    def ts(i: int) -> int:
        return candles[min(i, last)].ts

    lots = []
    for lot in reading.lots:
        if lot.end >= start:
            span = candles[lot.start : lot.end + 1]
            lots.append({"from": ts(lot.start), "to": ts(lot.end), "direction": lot.direction,
                         "low": min(c.low for c in span), "high": max(c.high for c in span),
                         "open_cause": lot.open_cause, "close_cause": lot.close_cause})
    regions = []
    for r in reading.regions:
        end = r.broken if r.broken is not None else r.expired
        if (end if end is not None else last) >= start:
            regions.append({"from": ts(r.created), "to": ts(end if end is not None else last), "low": r.low, "high": r.high,
                            "side": r.side, "code": r.code, "label": r.label, "page": r.page, "active": r.active})
    tags = [{"time": ts(t.index), "code": t.code, "label": t.label, "page": t.page, "direction": t.direction, "detail": t.detail}
            for t in reading.tags if t.index >= start]
    segments: list[dict] = []
    for i in range(start, len(candles)):
        name = reading.scenarios[i]
        if segments and segments[-1]["name"] == name:
            segments[-1]["to"] = ts(i)
        else:
            segments.append({"from": ts(i), "to": ts(i), "name": name})
    return {"asset": asset, "timeframe": timeframe, "lots": lots, "regions": regions, "tags": tags,
            "scenarios": segments, "scenario": reading.scenarios[-1]}


def wiki_marks(candles: Sequence[Candle], start: int = 0) -> list[dict]:
    """Setas do script WIKI PRO. Como as do LDP, só desenho."""
    return [{"time": s.ts, "direction": s.direction.value, "setup": s.setup}
            for s in WikiProV21().scan(candles)[start:] if s is not None]


def order_entries(orders: Sequence[dict], signals: Sequence[dict], timeframe: int, first_ts: int) -> list[dict]:
    """Ordens que foram para a corretora, na vela em que entraram."""
    by_id = {s["id"]: s for s in signals if "id" in s}
    out = []
    for o in orders:
        if o["status"] in NOT_SENT:
            continue
        signal = by_id.get(o.get("signal_id"))
        if signal is not None:
            ts = signal["entry_ts"]
        elif o["strategy"] == MANUAL:  # pode vencer minutos depois: a marca fica na vela em que você entrou
            ts = o["requested_at"] - o["requested_at"] % timeframe
        else:  # sem o sinal à mão: a ordem vence no fim da vela em que entrou
            end = o.get("expires_at")
            ts = end - timeframe if end else o["requested_at"] - o["requested_at"] % timeframe
        if ts < first_ts:
            continue
        price = o.get("ref_price")
        if price is None and signal is not None:
            price = signal.get("entry_price")
        out.append({"id": o["id"], "signal_id": o.get("signal_id"), "time": ts, "direction": o["direction"], "price": price,
                    "status": o["status"], "profit": o.get("profit"), "amount": o["amount"], "account": o.get("account"),
                    "strategy": o["strategy"], "setup": signal["setup"] if signal is not None else None})
    out.sort(key=lambda e: (e["time"], e["id"]))
    return out


def build_chart(
    asset: str,
    timeframe: int,
    candles: Sequence[Candle],
    limit: int,
    signals: list[dict],
    engine: LdpEngine | None,
    step: EngineStep | None,
    forming: Candle | None = None,
    orders: Sequence[dict] = (),
    show_wiki: bool = False,
) -> dict:
    start = max(0, len(candles) - limit)
    view = candles[start:]
    first_ts = view[0].ts if view else 0
    markers = []
    for s in signals:
        # Entrada dentro da vela (apostila): a seta vai na vela da entrada, não na da decisão.
        t = s["entry_ts"] if (s.get("details") or {}).get("intravela") else s["candle_ts"]
        if t >= first_ts:
            markers.append({"id": s["id"], "time": t, "strategy": s["strategy"], "direction": s["direction"], "result": s["result"],
                            "setup": s["setup"], "origin": s["origin"], "profit": s["profit"]})
    markers.sort(key=lambda m: m["time"])
    last_close = view[-1].close if view else None
    return {
        "asset": asset,
        "timeframe": timeframe,
        "candles": [candle_dict(c) for c in view],
        "forming": candle_dict(forming) if forming else None,
        **ldp_overlay(candles, start, forming.ts if forming else None),
        "wiki_marks": wiki_marks(candles, start) if show_wiki else [],
        "entries": order_entries(orders, signals, timeframe, first_ts),
        "markers": markers,
        "levels": nearby_levels(engine, last_close) if engine is not None and last_close is not None else [],
        "reading": reading(engine, step),
    }
