"""Stop loss que acompanha o lucro (10/11/2026): o limite conta do melhor resultado da sessão, não do Iniciar."""

from app.risk import RiskConfig, RiskManager
from tests.test_config import make_client

BASE = dict(stake=2, stop_win=None, max_trades=None, max_consecutive_losses=None)


def win(r, n=1, profit=1.7):
    for _ in range(n):
        r.opened(2)
        r.closed("win", profit, 2)


def lose(r, n=1):
    for _ in range(n):
        r.opened(2)
        r.closed("loss", -2, 2)


def test_o_piso_sobe_com_o_melhor_resultado_e_nunca_desce():
    r = RiskManager(RiskConfig(stop_loss=10, stop_loss_trail=True, **BASE))
    assert r.stop_floor == -10  # sem lucro ainda: igual ao normal
    win(r, 10)  # +17
    assert (r.peak_pnl, r.stop_floor) == (17.0, 7.0)
    lose(r, 4)  # +9: o piso continua em +7
    assert (r.pnl, r.stop_floor) == (9.0, 7.0)
    assert r.check(0.85)[0]  # perder mais 2 deixa em +7: ainda cabe
    lose(r)
    ok, why = r.check(0.85)  # +7: mais uma perda iria a +5
    assert not ok and "acompanhando o lucro" in why and "+7.00" in why and "+17.00" in why


def test_desligado_conta_do_iniciar_como_antes():
    r = RiskManager(RiskConfig(stop_loss=10, **BASE))
    win(r, 10)
    lose(r, 5)
    assert r.stop_floor == -10 and r.check(0.85)[0]  # +7: longe dos -10
    assert r.peak_pnl == 17.0  # o melhor ponto é guardado mesmo desligado (ligar no meio da sessão já vale)


def test_ligar_no_meio_da_sessao_vale_na_hora():
    r = RiskManager(RiskConfig(stop_loss=10, **BASE))
    win(r, 10)
    lose(r, 5)  # +7, melhor ponto +17
    r.cfg = RiskConfig(stop_loss=10, stop_loss_trail=True, **BASE)  # o que set_config faz com o bot rodando
    assert r.stop_floor == 7.0 and not r.check(0.85)[0]


def test_ciclo_de_gale_inteiro_precisa_caber_acima_do_piso():
    cfg = dict(BASE, martingale=True, gale_levels=2)
    r = RiskManager(RiskConfig(stop_loss=50, stop_loss_trail=True, **cfg))
    win(r, 40, profit=1.66)  # +66,40
    assert r.stop_floor == 16.4
    r.pnl = 30.0  # caiu para +30: um G2 inteiro (2 + 4,41 + 9,73 = 16,14) iria a +13,86, abaixo do piso
    ok, why = r.check(0.83, None)
    assert not ok and "ciclo de martingale inteiro" in why
    r.pnl = 33.0  # +33 - 16,14 = +16,86: cabe
    assert r.check(0.83, None)[0]


def test_painel_recebe_o_piso():
    r = RiskManager(RiskConfig(stop_loss=10, stop_loss_trail=True, **BASE))
    win(r, 10)
    snap = r.snapshot(0.85)
    assert snap["peak_pnl"] == 17.0 and snap["stop_floor"] == 7.0 and snap["config"]["stop_loss_trail"] is True
    assert RiskManager(RiskConfig(stop_loss=None, **BASE)).snapshot()["stop_floor"] is None


def test_configuracao_salva_e_chega_no_risco(tmp_path):
    with make_client(tmp_path) as client:
        assert client.get("/api/config").json()["stop_loss_trail"] is False  # padrão: desligado, como era
        r = client.put("/api/config", json={"stop_loss": 50, "stop_loss_trail": True})
        assert r.status_code == 200 and r.json()["stop_loss_trail"] is True
        cfg = client.app.state.config.get()
        assert cfg.risk().stop_loss_trail is True and cfg.risk().stop_loss == 50


def test_reinicio_do_servidor_refaz_o_melhor_ponto(tmp_path):
    from tests.fakes import FakeBroker
    from tests.test_manual_order import manager
    from tests.test_watchdog import candles
    om, _ = manager(tmp_path, FakeBroker(candles()[0], []), stop_win=None, stop_loss=10, stop_loss_trail=True,
                    max_consecutive_losses=None)
    rows = [{"id": i, "requested_at": i, "strategy": "retracao_comando", "status": "win", "profit": 1.7, "amount": 2.0}
            for i in range(10)]
    rows += [{"id": 20 + i, "requested_at": 20 + i, "strategy": "retracao_comando", "status": "loss", "profit": -2.0,
              "amount": 2.0} for i in range(5)]
    om.restore(rows)
    snap = om.snapshot(0.85)
    assert (snap["pnl"], snap["peak_pnl"], snap["stop_floor"]) == (7.0, 17.0, 7.0) and snap["can_trade"] is False
