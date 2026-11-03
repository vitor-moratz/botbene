"""Monta os dados do gráfico do painel: velas, linhas do v1.3, sinais e marcações próximas."""

from __future__ import annotations

from collections.abc import Sequence

from app.ldp.engine import EngineStep, LdpEngine
from app.ldp.levels import Role
from app.market.candle import Candle
from app.strategies.ldp_v13 import LdpV13

LEVELS_EACH_SIDE = 3


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


def build_chart(
    asset: str,
    timeframe: int,
    candles: Sequence[Candle],
    limit: int,
    signals: list[dict],
    engine: LdpEngine | None,
    step: EngineStep | None,
    forming: Candle | None = None,
) -> dict:
    lines = LdpV13().analyze(candles)
    start = max(0, len(candles) - limit)
    view = candles[start:]
    buy_line, sell_line = [], []
    for k in range(start, len(candles)):
        ts = candles[k].ts
        b, s = lines.buy_line[k], lines.sell_line[k]
        buy_line.append({"time": ts, "value": b} if b is not None else {"time": ts})
        sell_line.append({"time": ts, "value": s} if s is not None else {"time": ts})
    first_ts = view[0].ts if view else 0
    markers = []
    for s in signals:
        # Entrada dentro da vela (apostila): a seta vai na vela da entrada, não na da decisão.
        t = s["entry_ts"] if (s.get("details") or {}).get("intravela") else s["candle_ts"]
        if t >= first_ts:
            markers.append({"time": t, "strategy": s["strategy"], "direction": s["direction"], "result": s["result"],
                            "setup": s["setup"], "origin": s["origin"], "profit": s["profit"]})
    markers.sort(key=lambda m: m["time"])
    last_close = view[-1].close if view else None
    return {
        "asset": asset,
        "timeframe": timeframe,
        "candles": [candle_dict(c) for c in view],
        "forming": candle_dict(forming) if forming else None,
        "buy_line": buy_line,
        "sell_line": sell_line,
        "markers": markers,
        "levels": nearby_levels(engine, last_close) if engine is not None and last_close is not None else [],
        "reading": reading(engine, step),
    }
