"""Cada estratégia do gale tem o seu ciclo, e o stop de ciclo para a sessão depois de N ciclos perdidos.

Caso de 09/11/2026: retração no comando e Bollinger + RCI marcadas no gale dividiam um ciclo só, com uma ordem
aberta por vez. A Bollinger entrava no início de quase toda vela e a retração (que dispara segundos depois) ficava
sem vaga: 6 dos 8 sinais dela depois das 13:38 não viraram ordem."""

from app.broker.base import OrderResult
from app.paper import LOSS, WIN
from app.risk import RiskConfig, RiskManager, gale_stake
from tests.fakes import FakeBroker
from tests.test_bot_service import make_bot
from tests.test_config import make_client
from tests.test_gale_espera import armed_approval
from tests.test_manual_order import manager
from tests.test_watchdog import candles

BB, RET = "bb_rci", "retracao_comando"
GALE = dict(stake=2, stop_win=None, stop_loss=None, max_trades=None, max_consecutive_losses=None,
            martingale=True, gale_levels=2, gale_strategies=(BB, RET))


def both(**extra):
    return RiskManager(RiskConfig(**(GALE | extra)))


def lose(r, strategy, stake):
    r.opened(stake, strategy)
    r.closed(LOSS, -stake, stake, strategy)


def test_cada_estrategia_tem_o_seu_ciclo():
    r = both()
    lose(r, BB, 2)
    assert r.next_stake(0.85, BB) == 4.36 and r.next_stake(0.85, RET) == 2  # a perda da Bollinger não mexe na retração
    lose(r, RET, 2)
    lose(r, RET, 4.36)
    assert r.cycle(RET).level == 2 and r.cycle(BB).level == 1
    assert r.next_stake(0.85, RET) == 9.49 and r.next_stake(0.85, BB) == 4.36
    r.opened(4.36, BB)
    r.closed(WIN, 3.71, 4.36, BB)  # a vitória fecha só o ciclo da Bollinger
    assert r.cycle(BB).level == 0 and r.cycle(RET).level == 2 and r.next_stake(0.85, RET) == 9.49


def test_ordem_aberta_de_uma_nao_segura_a_outra():
    r = both()
    r.opened(2, BB)
    ok, why = r.check(0.85, BB)
    assert not ok and "esperando" in why  # dentro do mesmo ciclo, uma ordem por vez
    assert r.check(0.85, RET)[0]  # a retração tem o seu ciclo: entra
    r.opened(2, RET)
    assert not r.check(0.85, RET)[0]
    r.closed(LOSS, -2, 2, BB)
    assert r.check(0.85, BB)[0] and not r.check(0.85, RET)[0]


def test_stop_loss_reserva_os_gales_que_faltam_nos_outros_ciclos():
    r = both(stop_loss=30)
    lose(r, BB, 2)  # Bollinger no gale 1: ainda pode perder 4,36 + 9,49 = 13,85
    # retração começando um ciclo inteiro: 2 + 15,85 + 13,85 = 31,70 > 30
    ok, why = r.check(0.85, RET)
    assert not ok and "outro ciclo" in why
    assert r.check(0.85, BB)[0]  # a Bollinger termina o ciclo dela: 2 + 13,85 = 15,85
    r = both(stop_loss=32)
    lose(r, BB, 2)
    assert r.check(0.85, RET)[0]  # 31,70 cabe em 32


def test_stop_loss_conta_o_gale_que_falta_depois_da_ordem_aberta():
    r = both(stop_loss=20)
    r.opened(2, BB)  # aberta no início do ciclo; se perder, ainda vêm 4,36 e 9,49
    # retração: aberta 2 + ciclo 15,85 + gales da Bollinger 13,85 = 31,70 > 20
    assert not r.check(0.85, RET)[0]
    r.closed(WIN, 1.7, 2, BB)
    assert r.check(0.85, RET)[0]  # ciclo da Bollinger fechado: só os 15,85 da retração


def test_quem_nao_usa_o_gale_tambem_respeita_os_ciclos_abertos():
    r = RiskManager(RiskConfig(**(GALE | {"gale_strategies": (BB,), "stop_loss": 16})))
    lose(r, BB, 2)  # -2, e a Bollinger ainda pode perder 4,36 + 9,49 = 13,85
    assert r.cycle_worst_case(0.85, BB) == 13.85
    ok, why = r.check(0.85, RET)  # entrada sem gale: 2 + 2 + 13,85 = 17,85 > 16
    assert not ok and "outro ciclo" in why
    assert r.check(0.85, BB)[0]  # a Bollinger termina o ciclo dela: 2 + 13,85 = 15,85 cabe em 16


def test_stop_de_ciclo_para_depois_de_n_ciclos_perdidos():
    r = both(gale_levels=1, max_lost_cycles=2)
    lose(r, BB, 2)
    lose(r, BB, 4.36)  # 1º ciclo perdido inteiro
    assert r.lost_cycles == 1 and r.check(0.85, BB)[0]
    lose(r, RET, 2)
    lose(r, RET, 4.36)  # 2º ciclo perdido, na outra estratégia: soma
    assert r.lost_cycles == 2
    for s in (BB, RET, None):  # para todas, como os outros stops
        ok, why = r.check(0.85, s)
        assert not ok and why == "stop de ciclo: 2 ciclos de gale perdidos (máximo 2)"


def test_ciclo_ganho_no_gale_nao_conta_como_perdido():
    r = both(gale_levels=2, max_lost_cycles=1)
    lose(r, BB, 2)
    lose(r, BB, 4.36)
    r.opened(9.49, BB)
    r.closed(WIN, 8.07, 9.49, BB)
    assert r.lost_cycles == 0 and r.check(0.85, BB)[0]
    lose(r, RET, 2)  # perda sem gale nenhum ainda: o ciclo continua
    assert r.lost_cycles == 0


def test_sem_stop_de_ciclo_nao_para():
    r = both(gale_levels=1)
    for _ in range(3):
        lose(r, BB, 2)
        lose(r, BB, 4.36)
    assert r.lost_cycles == 3 and r.check(0.85, BB)[0]


def test_snapshot_lista_os_ciclos_em_andamento():
    r = both(max_lost_cycles=3)
    snap = r.snapshot(0.85)
    assert snap["cycles"] == [] and snap["lost_cycles"] == 0 and snap["gale_level"] == 0
    assert snap["config"]["max_lost_cycles"] == 3
    lose(r, RET, 2)
    r.opened(2, BB)
    snap = r.snapshot(0.85)
    assert [(c["strategy"], c["gale_level"], c["gale_open"]) for c in snap["cycles"]] == [(BB, 0, True), (RET, 1, False)]
    ret = snap["cycles"][1]
    assert ret["next_stake"] == 4.36 and ret["cycle_stakes"] == [2.0] and ret["cycle_worst"] == 15.85
    # os campos de cima mostram o ciclo mais adiantado (painel antigo)
    assert snap["gale_level"] == 1 and snap["next_stake"] == 4.36 and snap["gale_open"] is False


def test_reinicio_refaz_cada_ciclo_e_os_ciclos_perdidos(tmp_path):
    broker = FakeBroker(candles()[0], [])
    om, _ = manager(tmp_path, broker, stop_win=None, stop_loss=None, max_consecutive_losses=None,
                    martingale=True, gale_levels=1, gale_strategies=(BB, RET), max_lost_cycles=5)
    om.restore([{"id": 1, "requested_at": 1, "strategy": BB, "status": "loss", "profit": -2.0, "amount": 2.0},
                {"id": 2, "requested_at": 2, "strategy": RET, "status": "loss", "profit": -2.0, "amount": 2.0},
                {"id": 3, "requested_at": 3, "strategy": RET, "status": "loss", "profit": -4.36, "amount": 4.36}])
    snap = om.snapshot(0.85)
    assert snap["lost_cycles"] == 1
    assert [(c["strategy"], c["gale_level"]) for c in snap["cycles"]] == [(BB, 1)]


def test_ordens_saem_com_o_gale_do_ciclo_de_cada_estrategia(tmp_path):
    broker = FakeBroker(candles()[0], [])
    broker.results[1] = OrderResult(LOSS, -2.0)  # 1ª ordem (Bollinger) perde
    om, db = manager(tmp_path, broker, stop_win=None, stop_loss=None, max_consecutive_losses=None,
                     martingale=True, gale_levels=1, gale_strategies=(BB, RET))
    for strategy in (BB, RET, BB):
        om.submit(asset="EURUSD-OTC", timeframe=60, strategy=strategy, direction="call", ref_price=1.1,
                  signal_id=None, payout=0.85)
    rows = sorted(db.list_orders(), key=lambda r: r["id"])
    assert [(r["strategy"], r["amount"], r["gale"]) for r in rows] == [(BB, 2.0, 0), (RET, 2.0, 0), (BB, 4.36, 1)]


def gale_bot_both(tmp_path):
    bot, broker, db, _ = make_bot(tmp_path, n_live=3, closing=False, strategies={BB: "operate", RET: "operate"})
    bot._bootstrap(broker)
    bot.mode, bot.order_strategies = "automatico_veto", {BB, RET}
    bot.orders.reset(RiskConfig(**(GALE | {"stop_loss": 50})))
    return bot, broker, db


def test_retracao_entra_com_a_ordem_da_bollinger_aberta(tmp_path):
    """O caso de 09/11: as duas no gale, a Bollinger com ordem aberta, e a retração dispara."""
    bot, broker, db = gale_bot_both(tmp_path)
    bot.orders.risk.opened(2.0, BB)
    ap = armed_approval(bot, broker, strategy=RET)
    bot._poll(broker)
    assert ap["status"] == "ordem enviada" and broker.tickets[0].amount == 2.0
    [o] = db.list_orders()
    assert o["strategy"] == RET and o["gale"] == 0


def test_retracao_espera_so_a_ordem_do_ciclo_dela(tmp_path):
    bot, broker, db = gale_bot_both(tmp_path)
    bot.orders.risk.opened(2.0, RET)  # a ordem anterior da retração ainda sem resultado
    ap = armed_approval(bot, broker, strategy=RET)
    bot._poll(broker)
    assert ap["status"] == "esperando resultado" and not broker.tickets
    bot.orders.risk.closed(LOSS, -2.0, 2.0, RET)
    assert bot._retry_gale_waits(ap["deadline"] - 3) is True
    assert broker.tickets[0].amount == gale_stake(2, 2, 0.8)
    assert db.list_orders()[0]["gale"] == 1


def test_stop_de_ciclo_na_configuracao(tmp_path):
    with make_client(tmp_path) as client:
        assert client.get("/api/config").json()["max_lost_cycles"] is None  # desligado por padrão
        r = client.put("/api/config", json={"martingale": True, "gale_strategies": [BB, RET], "max_lost_cycles": 2})
        assert r.status_code == 200 and r.json()["max_lost_cycles"] == 2
        assert client.get("/api/status").json()["risk"]["config"]["max_lost_cycles"] == 2
        assert client.put("/api/config", json={"max_lost_cycles": 0}).status_code == 422
        r = client.put("/api/config", json={"max_lost_cycles": None})
        assert r.status_code == 200 and r.json()["max_lost_cycles"] is None
