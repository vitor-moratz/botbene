"""Gale na vela logo depois da perda: o resultado da ordem anterior chega ~1 s depois da vela abrir. Em vez de
bloquear a entrada, o bot espera o resultado dentro da janela e manda a ordem com o valor certo."""

from app.paper import WIN
from app.risk import RiskConfig, gale_stake
from app.service.bot import WAIT_GALE
from tests.test_bot_service import armed_for, make_bot

BB, RET = "bb_rci", "retracao_comando"


def gale_bot(tmp_path, mode="automatico"):
    bot, broker, db, _ = make_bot(tmp_path, n_live=3, closing=False, strategies={BB: "operate", RET: "operate"})
    bot._bootstrap(broker)
    bot.mode, bot.order_strategies = mode, {BB, RET}
    bot.orders.reset(RiskConfig(stake=2, stop_win=None, stop_loss=None, max_trades=None, max_consecutive_losses=None,
                                martingale=True, gale_levels=2, gale_strategies=(BB,)))
    return bot, broker, db


def armed_approval(bot, broker, strategy=BB):
    nxt = broker.live[0]
    r = bot.runner()
    r.armed = [armed_for(bot, nxt, nxt.low, strategy=strategy)]  # a vela vai tocar o gatilho
    [ap] = bot._open_approvals(r, r.armed, now=nxt.ts - 1)
    return ap


def test_espera_o_resultado_e_sai_com_o_valor_do_gale(tmp_path):
    bot, broker, db = gale_bot(tmp_path)
    bot.orders.risk.opened(2.0, BB)  # a ordem anterior da Bollinger ainda não tem resultado
    ap = armed_approval(bot, broker)
    bot._poll(broker)  # o gatilho dispara: em vez de bloquear, espera
    assert ap["status"] == WAIT_GALE and not broker.tickets and not db.list_orders()
    assert bot._retry_gale_waits(ap["deadline"] - 5) is False  # ainda sem resultado: continua esperando
    assert ap["status"] == WAIT_GALE
    bot.orders.risk.closed("loss", -2.0, 2.0, BB)  # chega o resultado: perdeu
    assert bot._retry_gale_waits(ap["deadline"] - 3) is True
    assert ap["status"] == "ordem enviada"
    [t] = broker.tickets
    assert t.amount == gale_stake(2, 2, 0.8)  # valor do gale 1, calculado depois do resultado
    [o] = db.list_orders()
    assert o["strategy"] == BB and o["gale"] == 1


def test_se_a_anterior_ganhou_sai_com_o_valor_normal(tmp_path):
    bot, broker, db = gale_bot(tmp_path)
    bot.orders.risk.opened(2.0, BB)
    ap = armed_approval(bot, broker)
    bot._poll(broker)
    bot.orders.risk.closed(WIN, 1.6, 2.0, BB)
    bot._retry_gale_waits(ap["deadline"] - 3)
    assert ap["status"] == "ordem enviada" and broker.tickets[0].amount == 2.0
    assert db.list_orders()[0]["gale"] == 0


def test_janela_fecha_sem_resultado_bloqueia_e_nao_manda_ordem(tmp_path):
    bot, broker, db = gale_bot(tmp_path)
    bot.orders.risk.opened(2.0, BB)
    ap = armed_approval(bot, broker)
    bot._poll(broker)
    assert bot._retry_gale_waits(ap["deadline"] + 0.5) is True
    assert ap["status"] == "bloqueada" and "não chegou dentro da janela" in ap["note"]
    bot.orders.risk.closed("loss", -2.0, 2.0, BB)  # resultado atrasado: nada sai fora da janela
    bot._retry_gale_waits(ap["deadline"] + 2)
    assert not broker.tickets
    [o] = db.list_orders()  # mas a entrada fica no histórico como bloqueada, com o motivo
    assert o["status"] == "bloqueada" and o["strategy"] == BB and "não chegou dentro da janela" in o["error"]
    assert ap["order_id"] == o["id"]


def test_estrategia_sem_gale_nao_espera(tmp_path):
    bot, broker, db = gale_bot(tmp_path)
    bot.orders.risk.opened(2.0, BB)  # ordem do gale aberta não segura a retração
    ap = armed_approval(bot, broker, strategy=RET)
    bot._poll(broker)
    assert ap["status"] == "ordem enviada" and broker.tickets[0].amount == 2.0


def test_da_para_vetar_enquanto_espera(tmp_path):
    bot, broker, db = gale_bot(tmp_path, mode="automatico_veto")
    bot.orders.risk.opened(2.0, BB)
    ap = armed_approval(bot, broker)
    bot._poll(broker)
    assert ap["status"] == WAIT_GALE
    assert bot.decide(ap["id"], False)["status"] == "cancelado por você"
    bot.orders.risk.closed("loss", -2.0, 2.0, BB)
    bot._retry_gale_waits(ap["deadline"] - 3)
    assert not broker.tickets and not db.list_orders()


def test_sem_martingale_nada_muda(tmp_path):
    bot, broker, db = gale_bot(tmp_path)
    bot.orders.reset(RiskConfig(stake=2, stop_win=None, stop_loss=None, max_trades=None, max_consecutive_losses=None))
    bot.orders.risk.opened(2.0, BB)
    ap = armed_approval(bot, broker)
    bot._poll(broker)
    assert ap["status"] == "ordem enviada" and broker.tickets[0].amount == 2.0
