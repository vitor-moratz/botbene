"""Gale por estratégia: só as marcadas usam o gale, cada uma no seu ciclo; as outras entram sempre com o valor normal.
Os ciclos separados e o stop de ciclo estão em test_ciclo_por_estrategia.py."""

import json

from app.broker.base import OrderResult
from app.paper import LOSS
from app.risk import RiskConfig, RiskManager
from app.service.config_store import ConfigStore
from app.strategies.intra import INTRA_NAMES
from tests.fakes import FakeBroker
from tests.test_config import make_client
from tests.test_manual_order import manager
from tests.test_watchdog import candles

GALE = dict(stake=2, stop_win=None, stop_loss=None, max_trades=None, max_consecutive_losses=None,
            martingale=True, gale_levels=2)
BB, RET = "bb_rci", "retracao_comando"


def only_bb(**extra):
    return RiskManager(RiskConfig(gale_strategies=(BB,), **(GALE | extra)))


def test_so_a_estrategia_marcada_usa_o_gale():
    r = only_bb()
    assert r.uses_gale(BB) and not r.uses_gale(RET) and not r.uses_gale(None)
    r.opened(2, RET)
    r.closed("loss", -2, 2, RET)
    assert r.gale_level == 0 and r.next_stake(0.85, BB) == 2  # perda de quem não usa o gale não abre ciclo
    r.opened(2, BB)
    r.closed("loss", -2, 2, BB)
    assert r.gale_level == 1
    assert r.next_stake(0.85, BB) == 4.36
    assert r.next_stake(0.85, RET) == 2  # a outra continua no valor normal
    r.opened(2, RET)
    r.closed("win", 1.7, 2, RET)
    assert r.gale_level == 1 and r.cycle_loss == 2  # vitória de quem não usa o gale não fecha o ciclo
    r.opened(4.36, BB)
    r.closed("win", 3.71, 4.36, BB)
    assert r.gale_level == 0 and r.cycle_loss == 0


def test_ciclo_perdido_inteiro_volta_ao_valor_normal():
    r = only_bb()
    for stake in (2, 4.36, 9.49):
        assert r.next_stake(0.85, BB) == stake
        r.opened(stake, BB)
        r.closed("loss", -stake, stake, BB)
    assert r.gale_level == 0 and r.next_stake(0.85, BB) == 2


def test_uma_ordem_por_vez_so_entre_as_do_gale():
    r = only_bb()
    r.opened(2, RET)
    assert r.check(0.85, BB)[0]  # ordem aberta de outra estratégia não segura o gale
    r.opened(2, BB)
    ok, why = r.check(0.85, BB)
    assert not ok and "esperando" in why
    assert r.check(0.85, RET)[0]  # e a ordem do gale aberta não segura as outras
    r.closed("loss", -2, 2, BB)
    assert r.check(0.85, BB)[0]


def test_stop_loss_reserva_o_ciclo_so_para_quem_usa_o_gale():
    r = only_bb(stop_loss=10)
    ok, why = r.check(0.85, BB)
    assert not ok and "ciclo" in why  # 2 + 4,36 + 9,49 = 15,85 > 10
    assert r.check(0.85, RET)[0]  # sem gale: só 2


def test_trocar_a_lista_no_meio_nao_trava_o_gale():
    r = only_bb()
    r.opened(2, RET)
    r.cfg = RiskConfig(gale_strategies=(BB, RET), **GALE)
    assert not r.check(0.85, RET)[0]  # agora a aberta conta como do gale da retração
    assert r.check(0.85, BB)[0]  # e não segura a Bollinger, que tem o seu ciclo
    r.closed("win", 1.7, 2, RET)
    r.cfg = RiskConfig(gale_strategies=(BB,), **GALE)
    assert r.open_gale_orders == 0 and r.check(0.85, BB)[0]


def test_sem_lista_todas_usam_o_gale_cada_uma_no_seu_ciclo():
    r = RiskManager(RiskConfig(**GALE))
    r.opened(2, RET)
    assert r.check(0.85, BB)[0] and not r.check(0.85, RET)[0]
    r.closed("loss", -2, 2, RET)
    assert r.next_stake(0.85, RET) == 4.36 and r.next_stake(0.85, BB) == 2


def test_snapshot_mostra_o_valor_do_proximo_gale_e_a_lista():
    r = only_bb()
    r.opened(2, BB)
    r.closed("loss", -2, 2, BB)
    snap = r.snapshot(0.85)
    assert snap["gale_level"] == 1 and snap["next_stake"] == 4.36
    assert snap["config"]["gale_strategies"] == [BB]
    json.dumps(snap)


def submit(om, strategy):
    return om.submit(asset="EURUSD-OTC", timeframe=60, strategy=strategy, direction="call", ref_price=1.1,
                     signal_id=None, payout=0.85)


def test_ordens_do_bot_usam_o_gale_so_na_estrategia_marcada(tmp_path):
    broker = FakeBroker(candles()[0], [])
    broker.results[1] = OrderResult(LOSS, -2.0)  # 1ª ordem (Bollinger) perde
    broker.results[2] = OrderResult(LOSS, -2.0)  # 2ª (retração) perde
    om, db = manager(tmp_path, broker, stop_win=None, stop_loss=None, max_consecutive_losses=None,
                     martingale=True, gale_levels=1, gale_strategies=(BB,))
    submit(om, BB)
    submit(om, RET)
    submit(om, RET)
    submit(om, BB)
    rows = sorted(db.list_orders(), key=lambda r: r["id"])
    assert [(r["strategy"], r["amount"], r["gale"]) for r in rows] == [
        (BB, 2.0, 0), (RET, 2.0, 0), (RET, 2.0, 0), (BB, 4.36, 1)]
    assert om.snapshot(0.85)["gale_level"] == 0  # o gale ganhou: ciclo fechado


def test_reinicio_refaz_o_ciclo_so_com_as_ordens_do_gale(tmp_path):
    broker = FakeBroker(candles()[0], [])
    om, _ = manager(tmp_path, broker, stop_win=None, stop_loss=None, martingale=True, gale_levels=1, gale_strategies=(BB,))
    om.restore([{"id": 1, "requested_at": 1, "strategy": BB, "status": "loss", "profit": -2.0, "amount": 2.0},
                {"id": 2, "requested_at": 2, "strategy": RET, "status": "win", "profit": 1.7, "amount": 2.0}])
    snap = om.snapshot(0.85)
    assert snap["gale_level"] == 1 and snap["next_stake"] == 4.36 and snap["pnl"] == -0.3


def test_configuracao_pela_tela(tmp_path):
    with make_client(tmp_path) as client:
        body = client.get("/api/config").json()
        assert body["gale_strategies"] == [] and BB in body["strategy_names"]
        r = client.put("/api/config", json={"martingale": True})
        assert r.status_code == 422 and "marque pelo menos uma" in r.json()["detail"]
        r = client.put("/api/config", json={"martingale": True, "gale_strategies": [BB, BB]})
        assert r.status_code == 200 and r.json()["gale_strategies"] == [BB]
        assert client.put("/api/config", json={"gale_strategies": ["ldp_v13"]}).status_code == 422
        assert client.put("/api/config", json={"strategies": {BB: "operate"}}).status_code == 200  # pode operar
        risk = client.get("/api/status").json()["risk"]
        assert risk["config"]["gale_strategies"] == [BB] and risk["config"]["martingale"] is True


def test_config_antiga_com_martingale_continua_valendo_para_todas(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"martingale": True, "gale_levels": 2, "account": "REAL", "mode": "automatico_veto"}))
    cfg = ConfigStore(path).get()
    assert cfg.account == "REAL" and cfg.gale_strategies == list(INTRA_NAMES)
    assert cfg.risk().gale_strategies == tuple(INTRA_NAMES)
    path.write_text(json.dumps({"martingale": False, "account": "REAL"}))
    cfg = ConfigStore(path).get()
    assert cfg.account == "REAL" and cfg.gale_strategies == []


def test_bot_opera_a_bollinger_no_automatico_com_gale_so_nela(tmp_path):
    from app.paper import WIN
    from tests.test_bot_service import make_bot

    bot, broker, db, _ = make_bot(tmp_path, n_live=120, closing=False, strategies={BB: "operate", RET: "observe"})
    for i in range(1, 40, 2):  # ordens ímpares perdem, pares ganham
        broker.results[i] = OrderResult(LOSS, -2.0)
    cfg = bot.config.update({"mode": "automatico", "martingale": True, "gale_levels": 1, "gale_strategies": [BB],
                             "stop_win": None, "stop_loss": None, "max_trades": None, "max_consecutive_losses": None})
    bot._bootstrap(broker)
    bot.apply_config(cfg)
    bot.orders.reset(cfg.risk())
    for _ in range(400):
        bot._poll(broker)
    orders = sorted(db.list_orders(), key=lambda r: r["id"])
    sent = [o for o in orders if o["status"] in (WIN, LOSS)]
    assert len(sent) >= 4, orders
    assert {o["strategy"] for o in orders} == {BB}  # a retração só observa
    # cada ordem sai do sinal da Bollinger, no preço de entrada dele (1º preço da vela seguinte)
    sig = {s["id"]: s for s in db.list_signals(origin="ao_vivo", strategy=BB, limit=5000)}
    assert all(o["signal_id"] in sig and o["ref_price"] == sig[o["signal_id"]]["entry_price"] for o in sent)
    # perdeu → a próxima da Bollinger é o gale 1; ganhou (ou perdeu o gale) → volta à entrada normal
    for prev, cur in zip(sent, sent[1:]):
        if prev["status"] == LOSS and prev["gale"] == 0:
            assert cur["gale"] == 1 and cur["amount"] > 2
        else:
            assert cur["gale"] == 0 and cur["amount"] == 2


def test_snapshot_mostra_o_ciclo_para_o_painel():
    r = only_bb()
    snap = r.snapshot(0.85)
    assert snap["cycle_stakes"] == [] and snap["cycle_loss"] == 0 and snap["gale_open"] is False
    assert snap["cycle_worst"] == 15.85  # 2 + 4,36 + 9,49 se perder tudo
    r.opened(2, BB)
    assert r.snapshot(0.85)["gale_open"] is True
    r.closed("loss", -2, 2, BB)
    r.opened(2, RET)
    r.closed("loss", -2, 2, RET)  # perda de quem não usa o gale não entra no ciclo
    snap = r.snapshot(0.85)
    assert snap["gale_level"] == 1 and snap["cycle_stakes"] == [2.0] and snap["cycle_loss"] == 2
    assert snap["gale_open"] is False and snap["cycle_worst"] == 15.85
    r.opened(4.36, BB)
    assert r.snapshot(0.85)["gale_open"] is True
    r.closed("loss", -4.36, 4.36, BB)
    snap = r.snapshot(0.85)
    assert snap["gale_level"] == 2 and snap["cycle_stakes"] == [2.0, 4.36] and snap["next_stake"] == 9.49
    r.opened(9.49, BB)
    r.closed("win", 8.07, 9.49, BB)
    snap = r.snapshot(0.85)
    assert snap["gale_level"] == 0 and snap["cycle_stakes"] == [] and snap["cycle_loss"] == 0
    json.dumps(snap)


def test_reinicio_refaz_os_valores_do_ciclo(tmp_path):
    broker = FakeBroker(candles()[0], [])
    om, _ = manager(tmp_path, broker, stop_win=None, stop_loss=None, martingale=True, gale_levels=2, gale_strategies=(BB,))
    om.restore([{"id": 1, "requested_at": 1, "strategy": BB, "status": "loss", "profit": -2.0, "amount": 2.0},
                {"id": 2, "requested_at": 2, "strategy": BB, "status": "loss", "profit": -4.36, "amount": 4.36}])
    snap = om.snapshot(0.85)
    assert snap["cycle_stakes"] == [2.0, 4.36] and snap["cycle_loss"] == 6.36 and snap["gale_level"] == 2
