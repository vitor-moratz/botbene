"""Roda as estratégias na base de pesquisa e devolve uma linha por entrada, com as características
de cada uma (gatilho, marcação, confluências, hora...) para quebrar o acerto por grupo."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from datetime import datetime

from app.analytics.stats import Group, summarize, total
from app.analytics.timeline import BRT
from app.market.candle import Candle
from app.paper import judge, profit_units
from app.strategies import Strategy, default_strategies
from app.strategies.intra import run_intra
from app.strategies.ldp_apostila import ApostilaConfig, backtest, run_plans


def _hour(ts: int) -> int:
    return datetime.fromtimestamp(ts, BRT).hour


def apostila_entries(asset: str, candles: Sequence[Candle], subs: Iterable[Candle], payout: float,
                     cfg: ApostilaConfig | None = None, timeframe: int = 60) -> list[dict]:
    """Só a estratégia de marcações, com configuração ajustável (para testar variações)."""
    _, plans = run_plans(candles, cfg, timeframe)
    return _intra_rows(asset, candles, plans, subs, payout, timeframe)


def intra_entries(asset: str, candles: Sequence[Candle], subs: Iterable[Candle], payout: float,
                  strategies: Sequence | None = None, timeframe: int = 60) -> list[dict]:
    """Todas as estratégias de dentro da vela, como o bot roda (o score vê as velas de 5 s para a recorrência)."""
    subs = list(subs)
    _, plans = run_intra(candles, strategies, timeframe, subs)
    return _intra_rows(asset, candles, plans, subs, payout, timeframe)


def _intra_rows(asset, candles, plans, subs, payout, timeframe) -> list[dict]:
    out = []
    for e in backtest(candles, plans, subs, timeframe):
        s = e["setup"]
        out.append({
            "asset": asset, "strategy": s.strategy, "entry_ts": s.target_ts, "hour": _hour(s.target_ts),
            "direction": s.direction.value, "result": e["result"], "payout": payout,
            "profit": profit_units(e["result"], payout), "entry_price": e["entry_price"], "exit_price": e["exit_price"],
            "trigger": s.trigger, "source": s.level_sources[0] if s.level_sources else "",
            "strength": s.level_strength, "score": s.score, "confluences": dict(s.confluences),
        })
    return out


def close_entries(asset: str, candles: Sequence[Candle], payout: float,
                  strategies: Iterable[Strategy] | None = None, timeframe: int = 60) -> list[dict]:
    """Scripts de fechamento: entrada na abertura da vela seguinte, saída no fechamento dela."""
    out = []
    for strat in strategies if strategies is not None else default_strategies():
        for sig in strat.scan(candles):
            if sig is None or sig.index + 1 >= len(candles):
                continue
            nxt = candles[sig.index + 1]
            if nxt.ts != sig.ts + timeframe:
                continue
            result = judge(sig.direction.value, nxt.open, nxt.close)
            out.append({
                "asset": asset, "strategy": sig.strategy, "entry_ts": nxt.ts, "hour": _hour(nxt.ts),
                "direction": sig.direction.value, "result": result, "payout": payout,
                "profit": profit_units(result, payout), "entry_price": nxt.open, "exit_price": nxt.close,
                "trigger": sig.setup, "source": sig.setup, "strength": 0, "score": 0, "confluences": {},
            })
    return out


def split_ts(entries: Sequence[dict], fraction: float) -> int:
    """Instante que separa a parte de AJUSTE (antes) da parte de CONFERÊNCIA (depois)."""
    ts = sorted(e["entry_ts"] for e in entries)
    return ts[int(len(ts) * fraction)] if ts else 0


def fmt_group(g: Group, label: str | None = None) -> str:
    if not g.n:
        return f"{label or g.key:40s} sem entradas"
    return (f"{label or g.key:40s} n={g.n:4d}  acerto {g.winrate * 100:5.1f}%  "
            f"(IC95 {g.ci_low * 100:4.1f}–{g.ci_high * 100:4.1f}%)  resultado {g.profit:+7.2f}")


def table(entries: Sequence[dict], key: Callable[[dict], str], min_n: int = 1) -> list[str]:
    groups = sorted(summarize(entries, key), key=lambda g: -g.n)
    return [fmt_group(g) for g in groups if g.n >= min_n]


def headline(entries: Sequence[dict], label: str = "total") -> str:
    return fmt_group(total(entries), label)
