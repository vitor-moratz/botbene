"""Pesquisa · DeepLOB: rede em numpy igual à do PyTorch, só arma acima do limiar, silêncio no OTC."""

import random

import numpy as np
import pytest

from app.market.candle import Candle
from app.strategies import deeplob_net as net
from app.strategies.base import Direction
from app.strategies.deeplob import MODEL, NAME, DeepLobIQ
from app.strategies.intra import INTRA_NAMES, OBSERVE_ONLY, bind_asset, default_intra, run_intra
from app.strategies.ldp_apostila import backtest

T0 = 1_700_000_040  # início de minuto


def market(minutes: int, seed: int = 3):
    """Velas de 5 s (passeio aleatório) e as velas de 1 min feitas com elas."""
    rng = random.Random(seed)
    price, subs = 1.1000, []
    for i in range(minutes * 12):
        o = price
        c = o + rng.gauss(0, 0.00005)
        subs.append(Candle(ts=T0 + 5 * i, open=o, high=max(o, c) + abs(rng.gauss(0, 0.00002)),
                           low=min(o, c) - abs(rng.gauss(0, 0.00002)), close=c))
        price = c
    m1 = []
    for k in range(minutes):
        g = subs[12 * k:12 * k + 12]
        m1.append(Candle(ts=T0 + 60 * k, open=g[0].open, high=max(s.high for s in g), low=min(s.low for s in g), close=g[-1].close))
    return m1, subs


def model_with(tmp_path, threshold):
    p = net.load(MODEL)
    p["threshold"] = np.array(threshold)
    path = tmp_path / "m.npz"
    np.savez(path, **p)
    return path


def test_rede_numpy_igual_a_do_pytorch():
    p = net.load(MODEL)
    mine = np.array([net.forward(p, x) for x in p["ref_x"]])
    assert np.abs(mine - p["ref_logit"]).max() < 1e-4


def test_registrada_so_para_observar():
    assert NAME in INTRA_NAMES and NAME in OBSERVE_ONLY
    assert any(s.name == NAME for s in default_intra())


def test_aquece_ate_ter_100_velas_de_5s():
    m1, subs = market(5)
    _, plans = run_intra(m1, [DeepLobIQ()], subs=subs)
    assert all(not p.armed for p in plans)
    assert "aquecendo" in plans[-1].reasons[0]


def test_limiar_zero_arma_e_entra_no_primeiro_preco(tmp_path):
    m1, subs = market(14)
    _, plans = run_intra(m1, [DeepLobIQ(model_path=model_with(tmp_path, 0.0))], subs=subs)
    armed = [a for p in plans for a in p.armed]
    assert armed, "com limiar 0 toda vela pronta arma"
    a = armed[0]
    assert a.strategy == NAME and a.trigger == "deeplob" and a.direction is Direction.CALL
    assert a.target_ts == a.decision_ts + 60 and "DeepLOB" in a.setup_label
    rows = backtest(m1, plans, subs)
    first = {s.ts: s for s in subs}
    for r in rows:  # entrada no fechamento da 1ª vela de 5 s da vela seguinte (≈ 5 s depois)
        assert r["entry_price"] == first[r["setup"].target_ts].close


def test_limiar_um_nunca_arma(tmp_path):
    m1, subs = market(14)
    _, plans = run_intra(m1, [DeepLobIQ(model_path=model_with(tmp_path, 1.0))], subs=subs)
    assert not any(p.armed for p in plans)
    assert "sem entrada" in plans[-1].reasons[0]


def test_otc_fica_em_silencio(tmp_path):
    m1, subs = market(14)
    s = DeepLobIQ(model_path=model_with(tmp_path, 0.0))
    bind_asset([s], "EURUSD-OTC")
    _, plans = run_intra(m1, [s], subs=subs)
    assert not any(p.armed for p in plans)
    assert "OTC" in plans[-1].reasons[0]


def test_ao_vivo_monta_as_velas_de_5s_com_o_preco_lido():
    s = DeepLobIQ()
    k = T0
    for t, price in ((0.2, 1.0), (2.0, 1.2), (4.9, 0.9), (5.1, 0.95), (9.0, 1.05)):
        s.watch_forming(Candle(ts=k, open=1.0, high=1.2, low=0.9, close=price), k + t)
    assert list(s.bars) == [(k, 1.0, 1.2, 0.9, 0.9)]  # 1ª vela de 5 s fechou quando veio o preço do segundo 5
    assert s._cur == [k + 5, 0.95, 1.05, 0.95, 1.05]


def test_modelo_ausente_nao_derruba(tmp_path):
    m1, subs = market(12)
    _, plans = run_intra(m1, [DeepLobIQ(model_path=tmp_path / "nao_existe.npz")], subs=subs)
    assert not any(p.armed for p in plans)
    assert "modelo indisponível" in plans[-1].reasons[0]
