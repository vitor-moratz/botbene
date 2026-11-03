import pytest

from app.risk import RiskConfig, RiskManager, gale_stake


def test_valor_do_gale_recupera_o_ciclo_e_ganha_a_entrada():
    assert gale_stake(2, 2, 0.85) == 4.36  # ganhar 4,36 a 85% paga a perda de 2 e ainda rende 1,70
    assert gale_stake(2, 2, 0.85) * 0.85 - 2 == pytest.approx(1.7, abs=0.01)


def test_martingale_com_analise():
    r = RiskManager(RiskConfig(stake=2, stop_win=None, stop_loss=None, max_trades=None, max_consecutive_losses=None,
                               martingale=True, gale_levels=2))
    assert r.next_stake(0.85) == 2
    r.opened(2)
    assert not r.check(0.85)[0]  # com martingale, uma ordem por vez
    r.closed("loss", -2, 2)
    assert r.gale_level == 1 and r.next_stake(0.85) == 4.36
    r.opened(4.36)
    r.closed("loss", -4.36, 4.36)
    assert r.gale_level == 2 and r.next_stake(0.85) == 9.49
    r.opened(9.49)
    r.closed("loss", -9.49, 9.49)
    assert r.gale_level == 0 and r.next_stake(0.85) == 2  # ciclo perdido: volta à entrada normal
    r.opened(2)
    r.closed("loss", -2, 2)
    r.opened(4.36)
    r.closed("win", 3.71, 4.36)
    assert r.gale_level == 0 and r.cycle_loss == 0


def test_ciclo_so_comeca_se_o_pior_caso_couber_no_stop_loss():
    cfg = dict(stake=2, stop_win=None, max_trades=None, max_consecutive_losses=None, martingale=True, gale_levels=2)
    assert RiskManager(RiskConfig(stop_loss=16, **cfg)).check(0.85)[0]  # 2 + 4,36 + 9,49 = 15,85
    ok, why = RiskManager(RiskConfig(stop_loss=10, **cfg)).check(0.85)
    assert not ok and "ciclo" in why
    assert RiskManager(RiskConfig(stop_loss=10, stake=2, stop_win=None, max_trades=None)).check(0.85)[0]  # sem gale: só 2


def test_stop_loss_conta_o_pior_caso_das_abertas():
    r = RiskManager(RiskConfig(stake=5, stop_loss=12, stop_win=None, max_trades=None))
    assert r.check()[0]
    r.opened()
    r.opened()  # 2 abertas = até -10 no pior caso; uma 3ª poderia dar -15
    ok, why = r.check()
    assert not ok and "stop loss" in why


def test_stop_win_e_perdas_seguidas():
    r = RiskManager(RiskConfig(stake=2, stop_win=3, stop_loss=None, max_consecutive_losses=2))
    r.opened()
    r.closed("win", 1.7)
    assert r.check()[0]
    r.opened()
    r.closed("win", 1.7)
    assert not r.check()[0] and "stop win" in r.check()[1]
    r2 = RiskManager(RiskConfig(stake=2, stop_win=None, stop_loss=None, max_consecutive_losses=2))
    for _ in range(2):
        r2.opened()
        r2.closed("loss", -2)
    assert not r2.check()[0] and "perdas seguidas" in r2.check()[1]
    r2.reset()
    assert r2.check()[0]


def test_limite_de_entradas():
    r = RiskManager(RiskConfig(max_trades=1, stop_win=None, stop_loss=None))
    r.opened()
    assert not r.check()[0]
