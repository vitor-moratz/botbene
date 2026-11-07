"""Retroativo do dia: a contagem por par e estratégia e a carga que cobre desde a meia-noite."""

from datetime import datetime

from fastapi.testclient import TestClient

from app.analytics.timeline import BRT, period_start
from app.api.factory import create_app
from app.config import Settings
from app.db.database import Database
from app.market.candle import Candle, is_otc
from app.service.bot import MAX_SUB_CANDLES, BotService, _first_armed_today
from app.service.events import EventHub
from app.strategies.ldp_apostila import Plan
from tests.fakes import FakeBroker

NOW = int(datetime(2026, 11, 6, 15, 0, tzinfo=BRT).timestamp())
DAY_START = period_start("hoje", datetime(2026, 11, 6, 15, 0, tzinfo=BRT))


def candles_between(start: int, end: int, tf: int = 60) -> list[Candle]:
    return [Candle(ts, 1.1, 1.2, 1.0, 1.15) for ts in range(start, end, tf)]


class ClockBroker(FakeBroker):
    def __init__(self, history, sub=None):
        super().__init__(history, [], sub=sub)
        self.asked: dict[int, list[int]] = {}

    def server_time(self):
        return NOW

    def get_candles(self, asset, timeframe, count, end_ts=None):
        self.asked.setdefault(timeframe, []).append(count)
        return super().get_candles(asset, timeframe, count, end_ts)


def make_bot(tmp_path, broker):
    settings = Settings(_env_file=None, data_dir=tmp_path, history_candles=500)
    return BotService(settings, Database(settings.db_url()), EventHub(), lambda: broker, strategies_factory=list)


def test_grafico_carrega_desde_a_meia_noite(tmp_path):
    two_days = candles_between(NOW - 2 * 86400, NOW)
    broker = ClockBroker(two_days)
    bot = make_bot(tmp_path, broker)
    bot.configure(["EURUSD-OTC"], 60)
    bot._bootstrap(broker)
    first = bot.runner().store.closed[0].ts
    assert first <= DAY_START  # 15 h de hoje + aquecimento, mais do que as 500 velas do mínimo
    assert first == two_days[-((NOW - DAY_START) // 60 + 1 + 120)].ts


def test_cinco_segundos_so_vao_ate_a_primeira_entrada_armada_de_hoje(tmp_path):
    broker = ClockBroker([], sub=candles_between(NOW - 86400, NOW, 5))
    bot = make_bot(tmp_path, broker)
    armed_at = DAY_START + 3600
    subs = bot._fetch_subcandles(broker, "EURUSD-OTC", 60, 1000, armed_at)
    assert subs[0].ts <= armed_at and broker.asked[5] == [(NOW - armed_at + 60) // 5]
    # sem nada armado cedo (ou numa reconexão, sem `since`): fica no limite de sempre
    assert bot._fetch_subcandles(broker, "EURUSD-OTC", 60, 1000) and broker.asked[5][-1] == MAX_SUB_CANDLES
    assert bot._fetch_subcandles(broker, "EURUSD-OTC", 60, 1000, NOW - 60) and broker.asked[5][-1] == MAX_SUB_CANDLES


def test_reconexao_nao_busca_o_dia_inteiro_de_cinco_segundos(tmp_path, monkeypatch):
    two_days = candles_between(NOW - 2 * 86400, NOW)
    broker = ClockBroker(two_days, sub=candles_between(NOW - 86400, NOW, 5))
    bot = make_bot(tmp_path, broker)
    bot.config.update({"strategies": {"retracao_comando": "observe"}})
    bot.configure(["EURUSD-OTC"], 60)
    monkeypatch.setattr("app.service.bot._first_armed_today", lambda *a: DAY_START)
    bot._bootstrap(broker, full_day=False)
    assert broker.asked[5] == [MAX_SUB_CANDLES]
    bot._bootstrap(broker)
    assert broker.asked[5][-1] == (NOW - DAY_START + 60) // 5


def test_primeira_armada_ignora_ontem_e_velas_sem_setup():
    tf = 60
    candles = candles_between(DAY_START - 120, DAY_START + 180)
    plans = [Plan(index=i, armed=[], reasons=[]) for i in range(len(candles))]
    assert _first_armed_today(candles, plans, tf, DAY_START) is None
    plans[0].armed.append("ontem")  # a entrada dele seria ontem
    assert _first_armed_today(candles, plans, tf, DAY_START) is None
    plans[1].armed.append("vira o dia")  # decidida 23:59, entra 00:00 de hoje
    plans[3].armed.append("hoje")
    assert _first_armed_today(candles, plans, tf, DAY_START) == candles[1].ts


def add(db, asset, strategy, ts, result, origin="backtest", profit=0.0):
    db.add_signal(origin=origin, asset=asset, timeframe=60, is_otc=is_otc(asset), strategy=strategy, direction="call",
                  setup="s", candle_ts=ts - 60, entry_ts=ts, payout=0.85, result=result, profit=profit)


def test_contagem_do_retroativo_por_par_e_estrategia(tmp_path):
    settings = Settings(_env_file=None, data_dir=tmp_path, history_candles=500)
    with TestClient(create_app(settings=settings, broker_factory=lambda: FakeBroker([], []))) as client:
        db = client.app.state.db
        today = period_start("hoje")
        add(db, "EURUSD-OTC", "retracao_comando", today + 600, "win", profit=0.85)
        add(db, "EURUSD-OTC", "retracao_comando", today + 1200, "loss", profit=-1.0)
        add(db, "EURUSD-OTC", "retracao_comando", today + 1800, "empate")
        add(db, "EURUSD-OTC", "retracao_lote", today + 600, "win", profit=0.85)
        add(db, "GBPUSD-op", "retracao_comando", today + 900, "loss", profit=-1.0)
        add(db, "GBPUSD-op", "retracao_lote", today + 2400, "pendente")  # sem resultado ainda: não conta
        add(db, "GBPUSD-op", "reversao_forca", today + 2400, "win", origin="ao_vivo", profit=0.85)  # ao vivo: não é retroativo
        add(db, "AUDUSD-op", "retracao_comando", today - 600, "win", profit=0.85)  # ontem

        data = client.get("/api/backtest/today").json()

    assert data["since_ts"] == today
    groups = {(g["asset"], g["strategy"]): g for g in data["groups"]}
    assert set(groups) == {("EURUSD-OTC", "retracao_comando"), ("EURUSD-OTC", "retracao_lote"), ("GBPUSD-op", "retracao_comando")}
    main = groups[("EURUSD-OTC", "retracao_comando")]
    assert (main["wins"], main["losses"], main["draws"]) == (1, 1, 1)
    assert main["profit"] == -0.15
    assert (main["first_ts"], main["last_ts"]) == (today + 600, today + 1800)
