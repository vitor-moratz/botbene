"""Base de pesquisa: download paginado e avaliação das estratégias."""

from app.config import Settings
from app.paper import judge
from app.research.dataset import download, load, research_db
from app.research.evaluate import close_entries, split_ts
from tests.fakes import FakeBroker
from tests.helpers import random_walk


def test_baixa_de_tras_para_frente_ate_o_inicio(tmp_path):
    candles = random_walk(2500, seed=3)
    broker = FakeBroker(candles, [], archive=candles)
    db = research_db(Settings(_env_file=None, data_dir=tmp_path))
    n = download(broker, db, "EURUSD", 60, since_ts=candles[300].ts, end_ts=candles[-1].ts + 60)
    got = load(db, "EURUSD", 60)
    assert n == 2200
    assert [c.ts for c in got] == [c.ts for c in candles[300:]]  # sem buracos nas emendas dos lotes
    assert broker.get_candles_calls == 3
    assert db.candle_series()[0]["count"] == 2200


def test_para_quando_a_corretora_nao_tem_mais(tmp_path):
    candles = random_walk(1500, seed=4)
    broker = FakeBroker(candles, [], archive=candles)
    db = research_db(Settings(_env_file=None, data_dir=tmp_path))
    assert download(broker, db, "EURUSD", 60, since_ts=0, end_ts=candles[-1].ts + 60) == 1500


def test_scripts_de_fechamento_entram_na_vela_seguinte():
    candles = random_walk(600, seed=5)
    by_ts = {c.ts: c for c in candles}
    entries = close_entries("EURUSD", candles, 0.85)
    assert entries
    for e in entries:
        c = by_ts[e["entry_ts"]]
        assert e["entry_price"] == c.open and e["exit_price"] == c.close
        assert e["result"] == judge(e["direction"], c.open, c.close)
    cut = split_ts(entries, 0.6)
    assert 0 < sum(e["entry_ts"] < cut for e in entries) < len(entries)
