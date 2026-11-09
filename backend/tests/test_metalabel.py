"""Meta-labeling da retração no comando: o conjunto de dados sai do mesmo replay do bot e só usa o passado."""

import argparse
import csv
import math
import random

import pytest

from app.config import Settings
from app.market.candle import Candle
from app.research.dataset import research_db
from app.research.metalabel import FEATURES, TouchSnapshot, add_recent_wr, build_dataset, entries_for_asset, features
from app.strategies.intra import run_intra
from app.strategies.ldp_apostila import backtest
from app.strategies.retracao_comando import RetracaoComando, RetracaoComandoV2
from tests.test_bot_service import armed_for, make_bot

T0 = 1_700_000_040 - 1_700_000_040 % 60


def synth(minutes=2500, seed=3):
    """Velas de 5 s com saltos de vez em quando (para ter velas de comando) e as M1 agregadas delas."""
    rnd = random.Random(seed)
    price, subs, pull = 1.1, [], 0
    for m in range(minutes):
        drift = 0.0
        if pull:  # minuto seguinte ao comando: metade das vezes recua forte nos primeiros 15 s
            drift_first, pull = (-pull * 0.00012 if rnd.random() < 0.5 else 0.0), 0
        else:
            drift_first = 0.0
            if rnd.random() < 0.04:  # vela de comando
                pull = rnd.choice((1, -1))
                drift = pull * 0.00012
        for k in range(12):
            i = 12 * m + k
            o = price
            c = o + rnd.gauss(0, 0.00004) + drift + (drift_first if k < 3 else 0.0)
            subs.append(Candle(T0 + 5 * i, o, max(o, c) + abs(rnd.gauss(0, 0.00001)), min(o, c) - abs(rnd.gauss(0, 0.00001)), c))
            price = c
    m1 = []
    for j in range(minutes):
        b = subs[12 * j:12 * j + 12]
        m1.append(Candle(b[0].ts, b[0].open, max(x.high for x in b), min(x.low for x in b), b[-1].close))
    return m1, subs


@pytest.fixture(scope="module")
def data():
    return synth()


def bot_entries(m1, subs, strategy):
    _, plans = run_intra(m1, [strategy])
    return {(e["setup"].target_ts, e["entry_price"], e["result"]) for e in backtest(m1, plans, subs)}


def test_mesmas_entradas_do_replay_do_bot(data):
    m1, subs = data
    rows = entries_for_asset("EURUSD-op", m1, subs)
    assert len(rows) > 20
    assert {(r["entry_ts"], r["entry_price"], r["result"]) for r in rows} == bot_entries(m1, subs, RetracaoComando())
    v2 = {(r["entry_ts"], r["entry_price"], r["result"]) for r in rows if r["is_v2"]}
    assert v2 == bot_entries(m1, subs, RetracaoComandoV2()) and 0 < len(v2) < len(rows)


def test_variaveis_nao_olham_o_futuro(data):
    m1, subs = data
    full = {r["entry_ts"]: r for r in entries_for_asset("EURUSD-op", m1, subs)}
    cut = 1800
    part = {r["entry_ts"]: r for r in entries_for_asset("EURUSD-op", m1[:cut], subs[:cut * 12])}
    assert len(part) > 10
    for ts, r in part.items():
        for f in FEATURES:
            a, b = r.get(f), full[ts].get(f)
            assert (a == b) or (a != a and b != b), (ts, f)


def test_toda_entrada_tem_a_lista_completa_e_resultado(data):
    m1, subs = data
    for r in entries_for_asset("EURUSD-op", m1, subs):
        assert set(FEATURES) - {"recent_wr"} <= set(r)
        assert r["result"] in ("win", "loss", "empate") and 0 < r["touch_ts"] - r["entry_ts"] <= 15
        assert r["run_length"] >= 1 and r["cmd_range_atr"] >= 1.5 and r["cmd_body_ratio"] >= 0.6


def test_acerto_recente_so_com_entradas_ja_vencidas():
    rows = [{"market": "op", "entry_ts": 60 * i, "touch_ts": 60 * i + 10, "result": "win" if i % 2 else "loss"} for i in range(30)]
    add_recent_wr(rows)
    assert math.isnan(rows[4]["recent_wr"])  # só 4 vencidas antes do toque da 5ª
    assert rows[5]["recent_wr"] == pytest.approx(2 / 5)  # 0..4: perdeu, ganhou, perdeu, ganhou, perdeu
    assert rows[29]["recent_wr"] == pytest.approx(10 / 20)


def test_sentimento_do_nosso_lado():
    from app.strategies.base import Direction
    from app.strategies.ldp_apostila import ArmedSetup
    candles = [Candle(T0 + 60 * i, 1.0, 1.001, 0.999, 1.0005 if i % 2 else 0.9995) for i in range(30)]
    candles.append(Candle(T0 + 1800, 1.0, 1.004, 1.0, 1.0035))
    setup = ArmedSetup(direction=Direction.PUT, trigger="comando", level_price=1.0, level_strength=0, level_sources=[],
                       decision_index=30, decision_ts=T0 + 1800, target_ts=T0 + 1860, window_seconds=15, touch_tol=0.0,
                       prev_close=1.0035, prev_range=0.004, gap_tol_pct=0.1)
    snap = TouchSnapshot(open=1.0035, high=1.005, low=1.003, price=1.0049, sec=10, mood=0.8, mood_age=2.0, mood_60s=0.6)
    f = features(setup, candles, snap, run_length=1, otc=True)
    assert f["mood_side"] == pytest.approx(0.2)  # PUT: 20% do nosso lado
    assert f["mood_chg_fav"] == pytest.approx(-0.2)  # a maioria foi para ACIMA, contra nós
    assert f["otc"] == 1.0 and f["touch_sec"] == 10


def test_montar_pela_base_de_pesquisa_com_sentimento(tmp_path, data, monkeypatch):
    m1, subs = data
    settings = Settings(_env_file=None, data_dir=tmp_path)
    db = research_db(settings)
    db.save_candles("EURUSD-OTC", 60, m1)
    db.save_candles("EURUSD-OTC", 5, subs)
    db.save_mood([("EURUSD-OTC", s.ts, 0.7, 1.0) for s in subs])
    rows = build_dataset(db, ["EURUSD-OTC"])
    assert rows and all(r["market"] == "OTC" for r in rows)
    assert all(r["mood_side"] == pytest.approx(0.7 if r["direction"] == "call" else 0.3) for r in rows)
    assert any(r["recent_wr"] == r["recent_wr"] for r in rows)

    from app.tools import metalabel as tool
    monkeypatch.setattr(tool, "get_settings", lambda: settings)
    out = tmp_path / "ds.csv"
    tool.cmd_montar(argparse.Namespace(ativos="", saida=str(out)))
    with out.open() as fh:
        read = list(csv.DictReader(fh))
    assert len(read) == len(rows) and set(FEATURES) <= set(read[0])
    tool.cmd_relatorio(argparse.Namespace(entrada=str(out)))


def test_sinal_ao_vivo_grava_o_toque_e_o_sentimento(tmp_path):
    bot, broker, db, _ = make_bot(tmp_path, n_live=3)
    bot._bootstrap(broker)
    bot._broker = broker
    broker.moods = {"EURUSD": (0.64, 3.2)}
    nxt = broker.live[0]
    bot.runner().armed = [armed_for(bot, nxt, nxt.low)]
    bot._poll(broker)
    row = db.list_signals(origin="ao_vivo", strategy="ldp_apostila")[0]
    touch = row["details"]["touch"]
    assert touch["price"] == nxt.close and 0 <= touch["sec"] <= 15 and touch["open"] == nxt.open
    assert row["details"]["mood"] == {"value": 0.64, "age": 3.2}
