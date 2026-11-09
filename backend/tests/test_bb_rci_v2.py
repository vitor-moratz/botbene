"""Bollinger + RCI v2: a v1 só com Gator dormindo, MACD virando e (onde há volume) Weis Wave mais fraca."""

import pytest

import app.strategies.bb_rci_confluencias as conf_mod
import app.strategies.bb_rci_v2 as v2_mod
from app.market.candle import Candle
from app.strategies.base import Direction
from app.strategies.bb_rci import NAME as V1, BollingerRci
from app.strategies.bb_rci_confluencias import (fractal_near, gator_sleeping, macd_turning, v2_passes, weis_exhausted,
                                                weis_waves)
from app.strategies.bb_rci_v2 import NAME as V2, BollingerRciV2
from app.strategies.intra import INTRA_NAMES, OBSERVE_ONLY, run_intra
from tests.helpers import T0
from tests.test_bb_rci import RALLY, flat_then
from tests.test_config import make_client


def candles_from(closes, vols=None, rng=0.004):
    out, prev = [], closes[0]
    for i, c in enumerate(closes):
        o = prev
        out.append(Candle(ts=T0 + 60 * i, open=o, high=max(o, c) + rng / 2, low=min(o, c) - rng / 2, close=c,
                          volume=(vols[i] if vols else 0.0)))
        prev = c
    return out


def test_gator_dorme_quando_a_tendencia_para_e_acorda_quando_acelera():
    accel = candles_from([1.0 + 0.0001 * i * i for i in range(90)])
    assert gator_sleeping(accel) is False  # as médias se afastam cada vez mais
    stop = candles_from([1.0 + 0.002 * i for i in range(60)] + [1.12] * 40)
    assert gator_sleeping(stop) is True  # parou: as médias se juntam
    assert gator_sleeping(candles_from([1.0] * 10)) is None  # aquecendo


def test_macd_virando_a_favor_da_entrada():
    # queda forte e, nas 2 últimas velas, mais lenta: histograma ainda negativo, mas subindo
    slowing = candles_from([2.0 - 0.003 * i for i in range(50)] + [1.85 - 0.0005 * i for i in range(2)])
    assert macd_turning(slowing, Direction.CALL) is True  # queda perdendo força: favorece CALL
    assert macd_turning(slowing, Direction.PUT) is False
    faster = candles_from([2.0 - 0.0001 * i * i for i in range(70)])
    assert macd_turning(faster, Direction.CALL) is False  # queda acelerando: não favorece CALL


def waves_case(down1_vol, down2_vol):
    # desce 6 velas, sobe 3, desce 6 (cada vela anda 0,01; a virada mínima é 0,5 ATR ~ 0,0055)
    closes = [1.0 - 0.01 * i for i in range(7)]
    closes += [closes[-1] + 0.01 * i for i in range(1, 4)]
    closes += [closes[-1] - 0.01 * i for i in range(1, 7)]
    vols = [down1_vol] * 7 + [10] * 3 + [down2_vol] * 6
    return candles_from(closes, vols, rng=0.001)


def test_weis_wave_queda_com_menos_volume_favorece_call():
    weak = waves_case(down1_vol=100, down2_vol=20)
    waves, current = weis_waves(weak)
    assert [w[0] for w in waves] == [-1, 1] and current[0] == -1
    assert weis_exhausted(weak, Direction.CALL) is True
    strong = waves_case(down1_vol=20, down2_vol=100)
    assert weis_exhausted(strong, Direction.CALL) is False  # queda com mais volume: empurrão de verdade


def test_weis_wave_sem_volume_fica_de_fora():
    otc = waves_case(100, 20)
    otc = [Candle(ts=c.ts, open=c.open, high=c.high, low=c.low, close=c.close, volume=0.0) for c in otc]
    assert weis_waves(otc) is None and weis_exhausted(otc, Direction.CALL) is None


def test_fractal_confirmado_perto_do_toque():
    lows = [1.010, 1.008, 1.000, 1.007, 1.009, 1.012, 1.011, 1.0005]  # fractal de baixa em 1,000; toque em 1,0005
    cs = [Candle(ts=T0 + 60 * i, open=l + 0.003, high=l + 0.004, low=l, close=l + 0.002) for i, l in enumerate(lows)]
    assert fractal_near(cs, Direction.CALL) is True
    far = cs[:-1] + [Candle(ts=cs[-1].ts, open=0.995, high=0.996, low=0.990, close=0.991)]
    assert fractal_near(far, Direction.CALL) is False


def test_regra_da_v2():
    assert v2_passes({"gator": True, "macd": True, "weis": True, "fractal": False})
    assert v2_passes({"gator": True, "macd": True, "weis": None, "fractal": None})  # OTC: sem volume, Weis não conta
    assert not v2_passes({"gator": True, "macd": True, "weis": False, "fractal": True})
    assert not v2_passes({"gator": False, "macd": True, "weis": True, "fractal": True})
    assert not v2_passes({"gator": True, "macd": None, "weis": True, "fractal": True})


@pytest.fixture
def forced(monkeypatch):
    def force(conf):
        monkeypatch.setattr(conf_mod, "confluences", lambda candles, direction, cfg=None: dict(conf))
        monkeypatch.setattr(v2_mod, "confluences", lambda candles, direction, cfg=None: dict(conf))
    return force


def test_v2_entra_so_com_as_confluencias_e_a_v1_anota(forced):
    candles = flat_then(*RALLY)
    forced({"gator": True, "macd": True, "weis": None, "fractal": False})
    _, plans = run_intra(candles, [BollingerRci(), BollingerRciV2()])
    armed = {a.strategy: a for a in plans[-1].armed}
    assert set(armed) == {V1, V2}
    assert armed[V2].direction is armed[V1].direction is Direction.PUT
    assert armed[V2].trigger == "bb_rci_v2" and "Gator dormindo" in armed[V2].setup_label
    assert armed[V1].extra["confluencias"]["gator"] is True  # a v1 só anota
    assert "extra" in armed[V1].to_dict()
    forced({"gator": False, "macd": True, "weis": True, "fractal": True})
    _, plans = run_intra(candles, [BollingerRci(), BollingerRciV2()])
    assert [a.strategy for a in plans[-1].armed] == [V1]  # Gator acordado: a v2 fica de fora, a v1 entra igual
    assert any("sem as confluências" in r for r in plans[-1].reasons)


def test_erro_nas_confluencias_nunca_impede_a_v1(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("falhou")
    monkeypatch.setattr(conf_mod, "confluences", boom)
    _, plans = run_intra(flat_then(*RALLY), [BollingerRci()])
    [a] = plans[-1].armed
    assert a.strategy == V1 and a.extra == {}


def test_v2_so_pode_observar(tmp_path):
    assert V2 in INTRA_NAMES and V2 in OBSERVE_ONLY
    with make_client(tmp_path) as client:
        assert client.put("/api/config", json={"strategies": {V2: "operate"}}).status_code == 422
        r = client.put("/api/config", json={"strategies": {V2: "observe", V1: "operate"}})
        assert r.status_code == 200 and r.json()["strategies"][V2] == "observe"
