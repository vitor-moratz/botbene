from __future__ import annotations

import logging
import os
import signal as os_signal
import threading
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, ValidationError, field_validator

from app.analytics.orders import MANUAL, order_rows, status_counts
from app.analytics.stats import breakeven, summarize, total
from app.analytics.timeline import BRT, GRANULARITY, cumulative, period_start, timeline
from app.analytics.validation import summarize_validation
from app.broker.base import BrokerError
from app.market.candle import is_otc, normalize_asset, valid_asset
from app.service.bot import BotBusyError, BotService
from app.service.config_store import MAX_ASSETS
from app.service.orders import DuplicateOrderError
from app.strategies import STRATEGY_LABELS, STRATEGY_ORDER

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")
Period = Literal["hoje", "7d", "mes", "geral"]
STOP_WAIT_SECONDS = 2  # o botão já mostra "Parando…"; o "parado" chega depois pelo websocket


def _bot(request: Request) -> BotService:
    return request.app.state.bot


def _norm_asset(v: str) -> str:
    v = normalize_asset(v)
    if not valid_asset(v):
        raise ValueError(f"ativo inválido: {v!r}")
    return v


class StartBody(BaseModel):
    """Sem nada: usa os ativos e a vela da Configuração."""

    asset: str | None = None
    assets: list[str] | None = Field(None, max_length=MAX_ASSETS)
    timeframe: Literal[60, 120, 300] | None = None

    @field_validator("asset")
    @classmethod
    def normalize(cls, v: str | None) -> str | None:
        return None if v is None else _norm_asset(v)

    @field_validator("assets")
    @classmethod
    def normalize_all(cls, v: list[str] | None) -> list[str] | None:
        return None if v is None else [_norm_asset(a) for a in v]


class FocusBody(BaseModel):
    asset: str


class ManualOrderBody(BaseModel):
    asset: str
    direction: Literal["call", "put"]
    amount: float = Field(gt=0, le=1_000_000)
    minutes: int = Field(ge=1, le=5)
    kind: Literal["binary", "digital"] = "binary"

    @field_validator("asset")
    @classmethod
    def normalize(cls, v: str) -> str:
        return _norm_asset(v)


class ConfigPatch(BaseModel):
    iq_email: str | None = Field(None, max_length=200)
    iq_password: str | None = Field(None, max_length=200)
    mode: Literal["sinais", "aprovacao", "automatico", "automatico_veto"] | None = None
    strategies: dict[str, Literal["off", "observe", "operate"]] | None = None
    chart_scripts: dict[str, bool] | None = None
    stake: float | None = None
    stop_win: float | None = None
    stop_loss: float | None = None
    max_trades: int | None = None
    max_consecutive_losses: int | None = None
    martingale: bool | None = None
    gale_levels: int | None = None
    gale_strategies: list[str] | None = None
    max_lost_cycles: int | None = None
    min_payout: float | None = None
    hours_start: str | None = None
    hours_end: str | None = None
    assets: list[str] | None = None
    timeframe: Literal[60, 120, 300] | None = None
    auto_market: bool | None = None
    option_type: Literal["binary", "digital", "best"] | None = None


def _strategies(strategy: str | None) -> str | list[str] | None:
    """`strategy` aceita um nome ou vários separados por vírgula."""
    if not strategy:
        return None
    names = [s.strip() for s in strategy.split(",") if s.strip()]
    return names[0] if len(names) == 1 else names


@router.get("/status")
def status(request: Request) -> dict:
    # ui_version: o painel recarrega sozinho quando o servidor sobe com arquivos novos.
    return _bot(request).snapshot() | {"ui_version": request.app.state.ui_version()}


@router.post("/bot/start")
def start(body: StartBody, request: Request) -> dict:
    bot = _bot(request)
    # `asset` (um par só) vem do painel antigo: ignorado, para valerem sempre os pares da Configuração.
    try:
        bot.start(body.assets, body.timeframe)
    except BotBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return bot.snapshot()


@router.post("/bot/focus")
def focus(body: FocusBody, request: Request) -> dict:
    bot = _bot(request)
    asset = normalize_asset(body.asset)
    if not valid_asset(asset):
        raise HTTPException(status_code=422, detail=f"Par inválido: {asset}")
    bot.set_focus(asset)
    return bot.snapshot()


@router.get("/pairs")
def pairs(request: Request) -> dict:
    return _bot(request).pairs_view()


@router.post("/orders/manual")
def manual_order(body: ManualOrderBody, request: Request) -> dict:
    try:
        return _bot(request).manual_order(body.asset, body.direction, body.amount, body.minutes, body.kind)
    except (BotBusyError, DuplicateOrderError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except BrokerError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/approvals/{approval_id}/{decision}")
def approval(approval_id: int, decision: Literal["aprovar", "rejeitar"], request: Request) -> dict:
    try:
        return _bot(request).decide(approval_id, decision == "aprovar")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Pedido de aprovação não encontrado") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/orders")
def orders(request: Request, period: Period = "hoje", limit: int = Query(200, ge=1, le=2000)) -> list[dict]:
    return request.app.state.db.list_orders(limit=limit, since_ts=period_start(period))


class AccountBody(BaseModel):
    account: Literal["PRACTICE", "REAL"]
    confirm: str | None = Field(None, max_length=20)


@router.get("/account")
def get_account(request: Request) -> dict:
    return _bot(request).account_info()


@router.post("/account")
def set_account(body: AccountBody, request: Request) -> dict:
    """Demo ou real. Só com o bot parado; a real exige `confirm` = "REAL"."""
    try:
        return _bot(request).switch_account(body.account, body.confirm)
    except BotBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/data/reset")
def reset_data(request: Request) -> dict:
    """Zera entradas, ordens, sessões e velas do bot (guarda uma cópia antes). Mantém pesquisa e configuração."""
    try:
        return _bot(request).reset_history()
    except BotBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/config")
def get_config(request: Request) -> dict:
    return request.app.state.config.public()


@router.put("/config")
def put_config(body: ConfigPatch, request: Request) -> dict:
    store = request.app.state.config
    patch = body.model_dump(exclude_unset=True)
    old_creds = store.credentials()
    try:
        cfg = store.update(patch)
    except ValidationError as exc:
        msg = "; ".join(e["msg"].removeprefix("Value error, ") for e in exc.errors())
        raise HTTPException(status_code=422, detail=msg) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    bot = _bot(request)
    if store.credentials() != old_creds:
        bot.invalidate_broker()
    bot.apply_config(cfg)
    out = store.public()
    out["applies_next_start"] = bot.running
    return out


@router.post("/config/test")
def test_config(request: Request) -> dict:
    try:
        return _bot(request).test_connection()
    except Exception as exc:  # noqa: BLE001 - qualquer falha de login vira mensagem na tela
        log.warning("Testar conexão falhou: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc) or type(exc).__name__) from exc


@router.post("/bot/stop")
def stop(request: Request) -> dict:
    bot = _bot(request)
    bot.stop(wait=STOP_WAIT_SECONDS)
    return bot.snapshot()


@router.post("/shutdown")
def shutdown(request: Request) -> dict:
    """Botão "Desligar" do programa: para o bot e encerra o servidor."""
    if not request.app.state.allow_shutdown:
        raise HTTPException(status_code=403, detail="Desligamento desativado neste servidor")
    _bot(request).stop(wait=12)
    threading.Timer(0.5, lambda: os.kill(os.getpid(), os_signal.SIGINT)).start()
    return {"ok": True}


@router.get("/chart")
def chart(request: Request, limit: int = Query(240, ge=50, le=1500), asset: str | None = None) -> dict:
    return _bot(request).chart(limit, normalize_asset(asset) if asset else None)


@router.get("/reading")
def reading(request: Request, limit: int = Query(240, ge=50, le=1500), asset: str | None = None) -> dict:
    return _bot(request).reading_view(limit, normalize_asset(asset) if asset else None)


@router.get("/strategies")
def strategies() -> list[dict]:
    return [{"name": name, "label": STRATEGY_LABELS.get(name, name)} for name in STRATEGY_ORDER]


@router.get("/signals")
def signals(
    request: Request,
    limit: int = Query(200, ge=1, le=5000),
    strategy: str | None = None,
    origin: str | None = None,
    result: str | None = None,
    asset: str | None = None,
    period: Period = "geral",
) -> list[dict]:
    return request.app.state.db.list_signals(
        limit=limit, strategy=_strategies(strategy), origin=origin, result=result, asset=asset, since_ts=period_start(period)
    )


@router.get("/validation")
def validation(request: Request) -> dict:
    """Placar de validação ao vivo das estratégias que operam; sem nenhuma operando, das que só observam.
    OTC fica de fora: é outro mercado, com estatística separada, e a pesquisa não cobriu."""
    db = request.app.state.db
    cfg = request.app.state.config.get()
    names = [n for n in STRATEGY_ORDER if n in (cfg.operating or cfg.running)]
    orders = [o for o in db.list_orders(limit=100_000) if not is_otc(o["asset"])]
    default_payout = request.app.state.bot.settings.default_payout

    def signals(name: str) -> list[dict]:
        return [s for s in db.resolved_signals(origin="ao_vivo", strategy=name) if not s["is_otc"]]

    return {"strategies": [
        summarize_validation(name, STRATEGY_LABELS.get(name, name), signals(name), orders, default_payout)
        for name in names
    ]}


@router.get("/backtest/today")
def backtest_today(request: Request) -> dict:
    """Retroativo de hoje, por par e estratégia: o painel soma conforme o que está à vista no gráfico."""
    since = period_start("hoje")
    by_key: dict[tuple[str, str], list[dict]] = {}
    for row in request.app.state.db.resolved_signals(origin="backtest", since_ts=since):  # em ordem de horário
        by_key.setdefault((row["asset"], row["strategy"]), []).append(row)
    groups = []
    for (asset, strategy), rows in by_key.items():
        t = total(rows)
        groups.append({"asset": asset, "strategy": strategy, "wins": t.wins, "losses": t.losses, "draws": t.draws,
                       "profit": t.profit, "first_ts": rows[0]["entry_ts"], "last_ts": rows[-1]["entry_ts"]})
    return {"since_ts": since, "groups": groups}


def _hour_brt(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(BRT).strftime("%H")


@router.get("/stats")
def stats(
    request: Request,
    origin: str | None = None,
    asset: str | None = None,
    strategy: str | None = None,
    period: Period = "geral",
) -> dict:
    since = period_start(period)
    rows = request.app.state.db.resolved_signals(origin=origin, asset=asset, strategy=_strategies(strategy), since_ts=since)
    overall = total(rows)
    order = {name: i for i, name in enumerate(STRATEGY_ORDER)}
    by_strategy = sorted(summarize(rows, lambda r: r["strategy"]), key=lambda g: order.get(g.key, 99))
    by_setup = sorted(summarize(rows, lambda r: f"{r['strategy']}|{r['setup']}"), key=lambda g: (-g.n, g.key))
    by_hour = sorted(summarize(rows, lambda r: _hour_brt(r["entry_ts"])), key=lambda g: g.key)
    by_market = summarize(rows, lambda r: "OTC" if r["is_otc"] else "Mercado normal")
    by_origin = summarize(rows, lambda r: r["origin"])
    return {
        "period": period,
        "since_ts": since,
        "granularity": GRANULARITY[period],
        "total": overall.to_dict(),
        "breakeven": overall.breakeven if overall.breakeven is not None else breakeven(0.85),
        "by_strategy": [g.to_dict() | {"label": STRATEGY_LABELS.get(g.key, g.key)} for g in by_strategy],
        "by_setup": [g.to_dict() for g in by_setup],
        "by_hour": [g.to_dict() for g in by_hour],
        "by_market": [g.to_dict() for g in by_market],
        "by_origin": [g.to_dict() for g in by_origin],
        "timeline": timeline(rows, period),
        "cumulative": cumulative(rows),
        "assets": request.app.state.db.assets(),
    }


@router.get("/stats/orders")
def order_stats(
    request: Request,
    period: Period = "mes",
    account: Literal["PRACTICE", "REAL"] | None = None,
    asset: str | None = None,
    strategy: str | None = None,
) -> dict:
    """Tela Desempenho: só ordens enviadas à corretora, em dinheiro. `account` separa demo de real (não se somam)."""
    db = request.app.state.db
    since = period_start(period)
    every = db.list_orders(limit=100_000)
    orders = [o for o in every if (since is None or o["requested_at"] >= since) and (account is None or o["account"] == account)]
    if asset:
        orders = [o for o in orders if o["asset"] == asset]
    names = _strategies(strategy)
    if names:
        wanted = {names} if isinstance(names, str) else set(names)
        orders = [o for o in orders if o["strategy"] in wanted]
    signals = db.signal_info(o["signal_id"] for o in orders)
    rows = order_rows(orders, signals, request.app.state.bot.settings.default_payout)
    overall = total(rows)
    order = {name: i for i, name in enumerate(STRATEGY_ORDER)}

    def label(name: str) -> str:
        return STRATEGY_LABELS.get(name) or ("Entrada manual" if name == MANUAL else name)

    by_strategy = sorted(summarize(rows, lambda r: r["strategy"]), key=lambda g: order.get(g.key, 99))
    mine = [o for o in every if account is None or o["account"] == account]  # o que dá para filtrar, em qualquer período
    return {
        "period": period,
        "since_ts": since,
        "account": account,
        "granularity": GRANULARITY[period],
        "total": overall.to_dict(),
        "breakeven": overall.breakeven if overall.breakeven is not None else breakeven(0.85),
        "staked": round(sum(r["amount"] for r in rows), 2),
        "by_strategy": [g.to_dict() | {"label": label(g.key)} for g in by_strategy],
        "by_setup": [g.to_dict() for g in sorted(summarize(rows, lambda r: f"{r['strategy']}|{r['setup']}"), key=lambda g: (-g.n, g.key))],
        "by_hour": [g.to_dict() for g in sorted(summarize(rows, lambda r: _hour_brt(r["entry_ts"])), key=lambda g: g.key)],
        "by_market": [g.to_dict() for g in summarize(rows, lambda r: "OTC" if r["is_otc"] else "Mercado normal")],
        "by_type": [g.to_dict() for g in sorted(summarize(rows, lambda r: "Digital" if r["option_type"] == "digital" else "Binária"),
                                                key=lambda g: g.key)],
        "timeline": timeline(rows, period),
        "cumulative": cumulative(rows),
        **status_counts(orders),
        "assets": sorted({o["asset"] for o in mine}),
        "strategies": [{"name": n, "label": label(n)} for n in sorted({o["strategy"] for o in mine}, key=lambda n: order.get(n, 99))],
    }
