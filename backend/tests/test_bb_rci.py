"""Bollinger + RCI: banda de Bollinger tocada com o RCI no extremo, entrada contra na vela seguinte."""

import pytest

from app.strategies.base import Direction
from app.strategies.bb_rci import NAME, BbRciConfig, BollingerRci, bollinger, decide, rci
from app.strategies.intra import run_intra
from tests.helpers import seq


def test_rci_subida_e_descida_em_fila():
    assert rci([1, 2, 3, 4, 5, 6, 7, 8, 9]) == pytest.approx(100)
    assert rci([9, 8, 7, 6, 5, 4, 3, 2, 1]) == pytest.approx(-100)


def test_rci_com_empates_usa_posicao_media():
    # 3 preços iguais no meio: posições de preço 4, 5 e 6 viram 5 para os três; tempo 6, 5, 4 → soma d² = 2
    assert rci([1, 2, 3, 5, 5, 5, 7, 8, 9]) == pytest.approx((1 - 6 * 2 / (9 * 80)) * 100)
    assert -100 < rci([5, 5, 5, 5, 5, 5, 5, 5, 6]) < 100


def test_bollinger_desvio_populacional():
    mid, up, lo = bollinger([1, 3] * 10, 2.0)
    assert mid == pytest.approx(2)
    assert up == pytest.approx(4) and lo == pytest.approx(0)  # desvio populacional de 1 e 3 = 1


def flat_then(*last):
    """19 velas paradas oscilando pouco, depois as velas dadas."""
    calm = [(10.00, 10.01, 9.99, 10.00 + (0.001 if i % 2 else -0.001)) for i in range(11)]
    return seq(*calm, *last)


RALLY = [(10.00 + i * 0.01, 10.02 + i * 0.01, 9.995 + i * 0.01, 10.01 + i * 0.01) for i in range(9)]


def test_subida_em_fila_ate_a_banda_de_cima_da_put():
    candles = flat_then(*RALLY)
    assert len(candles) == 20
    direction, why, nums = decide(candles, BbRciConfig())
    assert direction is Direction.PUT
    assert nums["rci"] == pytest.approx(100)
    assert "banda de cima" in why


def test_descida_em_fila_ate_a_banda_de_baixo_da_call():
    fall = [(10.00 - i * 0.01, 10.005 - i * 0.01, 9.98 - i * 0.01, 9.99 - i * 0.01) for i in range(9)]
    direction, _, nums = decide(flat_then(*fall), BbRciConfig())
    assert direction is Direction.CALL
    assert nums["rci"] == pytest.approx(-100)


def test_sem_entrada_dentro_das_bandas():
    # fechamentos 9,999 / 10,001 → desvio 0,001 e bandas em ±0,002; pavios de 0,0015 ficam dentro
    candles = seq(*[(10.00, 10.0015, 9.9985, 10.00 + (0.001 if i % 2 else -0.001)) for i in range(20)])
    direction, why, _ = decide(candles, BbRciConfig())
    assert direction is None and "dentro das bandas" in why


def test_buraco_nas_velas_nao_decide():
    candles = flat_then(*RALLY)
    gap = candles[:10] + [c.__class__(ts=c.ts + 300, open=c.open, high=c.high, low=c.low, close=c.close) for c in candles[10:]]
    direction, why, _ = decide(gap, BbRciConfig())
    assert direction is None and "aquecendo" in why


def test_rci_virando_espera_o_rci_cair():
    candles = flat_then(*RALLY)
    direction, why, _ = decide(candles, BbRciConfig(rci_turn=True))
    assert direction is None and "não virou" in why  # RCI ainda em +100, igual ao anterior


def test_no_motor_arma_entrada_no_inicio_da_vela_seguinte():
    candles = flat_then(*RALLY)
    _, plans = run_intra(candles, [BollingerRci()])
    armed = plans[-1].armed
    assert len(armed) == 1
    s = armed[0]
    assert s.strategy == NAME and s.trigger == "bb_rci" and s.direction is Direction.PUT
    assert s.target_ts == candles[-1].ts + 60
    assert s.touch_tol >= 1e9  # entra no 1º preço, sem esperar toque
    assert all(not p.armed for p in plans[:-1])
