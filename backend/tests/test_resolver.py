"""Pendentes resolvidos pelo histórico da IQ, sem depender do bot ligado."""

from app.config import Settings
from app.db.database import Database
from app.paper import judge
from app.service.resolver import PendingResolver
from tests.fakes import FakeBroker
from tests.helpers import random_walk


def pending(db, entry_ts, direction="call", entry_price=None):
    return db.add_signal(origin="ao_vivo", asset="EURUSD", timeframe=60, is_otc=False, strategy="ldp_v13",
                         direction=direction, setup="reteste", candle_ts=entry_ts - 60, entry_ts=entry_ts,
                         entry_price=entry_price, payout=0.8, details={}, result="pendente")


def make(tmp_path):
    candles = random_walk(200, seed=2)
    db = Database(Settings(_env_file=None, data_dir=tmp_path).db_url())
    broker = FakeBroker(candles[:100], [], archive=candles)
    return db, broker, candles


def test_resolve_pendentes_com_o_bot_desligado(tmp_path):
    db, broker, candles = make(tmp_path)
    a = pending(db, candles[150].ts)
    b = pending(db, candles[160].ts, direction="put", entry_price=candles[160].open + 0.0001)
    resolver = PendingResolver(db, lambda: broker)
    assert resolver.run_once(now=candles[-1].ts + 120) == 2
    rows = {r["id"]: r for r in db.list_signals(limit=10)}
    ca, cb = candles[150], candles[160]
    assert rows[a["id"]]["result"] == judge("call", ca.open, ca.close) and rows[a["id"]]["entry_price"] == ca.open
    # entrada dentro da vela (apostila): mantém o preço de entrada gravado
    assert rows[b["id"]]["entry_price"] == b["entry_price"]
    assert rows[b["id"]]["result"] == judge("put", b["entry_price"], cb.close)


def test_nao_mexe_no_que_ainda_nao_fechou(tmp_path):
    db, broker, candles = make(tmp_path)
    pending(db, candles[199].ts)
    resolver = PendingResolver(db, lambda: broker)
    assert resolver.run_once(now=candles[199].ts + 30) == 0
    assert broker.get_candles_calls == 0  # nem conecta à IQ sem necessidade


def test_cancela_se_a_vela_nao_existe_mais(tmp_path):
    db, broker, candles = make(tmp_path)
    p = pending(db, candles[-1].ts + 60 * 500)  # vela que a corretora não tem
    PendingResolver(db, lambda: broker, cancel_after=60).run_once(now=candles[-1].ts + 60 * 600)
    assert db.list_signals(limit=5)[0]["result"] == "cancelado"
    assert p is not None


def test_nao_resolve_duas_vezes(tmp_path):
    db, broker, candles = make(tmp_path)
    p = pending(db, candles[150].ts)
    assert db.resolve_signal(p["id"], entry=1.0, exit_=1.1, result="win", profit=0.8)
    assert not db.resolve_signal(p["id"], entry=1.0, exit_=0.9, result="loss", profit=-1.0)
    assert db.list_signals(limit=1)[0]["result"] == "win"
