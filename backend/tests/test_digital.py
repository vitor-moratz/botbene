"""Opção digital: vencimento, escolha do tipo (binária, digital ou maior payout), compra e resultado na IQ,
o bot mandando a ordem no tipo escolhido e a entrada manual digital."""

import calendar
import time
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.broker.base import BINARY, DIGITAL, BrokerError, OrderRefused, OrderTicket, digital_expiry_for, expiry_for
from app.broker.iqoption import DIGITAL_REFUSED_SECONDS, IQOptionBroker, _digital_instrument
from app.service.config_store import MAX_ASSETS, UserConfig
from app.service.product import Choice, Offer, choose, market_view
from tests.test_bot_service import approval_bot
from tests.test_config import make_client
from tests.test_manual_order import client as manual_client  # noqa: F401 - fixture
from tests.test_manual_order import pair, post
from tests.test_order_stats import T, order
from tests.test_watchdog import wait_for


def utc(h, m, s):
    return calendar.timegm((2026, 11, 8, h, m, s))


# ---------------------------------------------------------------- vencimento

def test_vencimento_da_digital():
    for sec in (0, 15, 29, 30, 45, 59):  # 1 min: a mesma regra da binária
        assert digital_expiry_for(utc(20, 35, sec)) == expiry_for(utc(20, 35, sec))
    assert digital_expiry_for(utc(20, 35, 25), 5) == utc(20, 40, 0)  # visto na IQ: às 20:35:25, a de 5 min vence 20:40
    assert digital_expiry_for(utc(20, 39, 29), 5) == utc(20, 40, 0)
    assert digital_expiry_for(utc(20, 39, 30), 5) == utc(20, 45, 0)  # 30 s ou menos: o seguinte
    assert digital_expiry_for(utc(20, 40, 0), 5) == utc(20, 45, 0)
    with pytest.raises(BrokerError, match="não tem vencimento de 3 min"):
        digital_expiry_for(utc(20, 35, 0), 3)


def test_codigo_da_digital_como_a_iq_usa():
    assert _digital_instrument(81, utc(20, 36, 0), 1, "call") == "do81A20261108D203600T1MCSPT"
    assert _digital_instrument(1861, utc(20, 40, 0), 5, "put") == "do1861A20261108D204000T5MPSPT"


# ---------------------------------------------------------------- escolha do tipo

OPEN_B, OPEN_D = Offer(True, "ok", 0.84), Offer(True, "ok", 0.87)
SHUT_B = Offer(False, "X está fechado para binária agora", 0.84)
SHUT_D = Offer(False, "X está fechado para digital agora", 0.87)


def test_escolha_fixa_respeita_a_configuracao_mesmo_fechada():
    assert choose("binary", {BINARY: OPEN_B, DIGITAL: OPEN_D}) == Choice(BINARY, True, "ok", 0.84)
    assert choose("digital", {BINARY: OPEN_B, DIGITAL: OPEN_D}) == Choice(DIGITAL, True, "ok", 0.87)
    assert choose("digital", {BINARY: OPEN_B, DIGITAL: SHUT_D}).ok is False  # não troca sozinho para a binária


def test_maior_payout_entre_os_abertos_e_binaria_no_empate():
    assert choose("best", {BINARY: OPEN_B, DIGITAL: OPEN_D}).kind == DIGITAL
    assert choose("best", {BINARY: Offer(True, "ok", 0.88), DIGITAL: OPEN_D}).kind == BINARY
    assert choose("best", {BINARY: Offer(True, "ok", 0.87), DIGITAL: OPEN_D}).kind == BINARY
    assert choose("best", {BINARY: SHUT_B, DIGITAL: OPEN_D}) == Choice(DIGITAL, True, "ok", 0.87)
    assert choose("best", {BINARY: OPEN_B, DIGITAL: Offer(True, "ok", None)}).kind == BINARY  # payout desconhecido perde
    both = choose("best", {BINARY: SHUT_B, DIGITAL: SHUT_D})
    assert not both.ok and "binária" in both.why and "digital" in both.why


def test_troca_de_mercado_olha_o_tipo_escolhido():
    p = {"open": False, "payout": 0.84, "next_open": 500, "next_close": None,
         "digital_open": True, "digital_payout": 0.87, "digital_next_open": None, "digital_next_close": 900}
    assert market_view(p, "binary") == {"open": False, "payout": 0.84, "next_open": 500, "next_close": None}
    assert market_view(p, "digital") == {"open": True, "payout": 0.87, "next_open": None, "next_close": 900}
    assert market_view(p, "best") == {"open": True, "payout": 0.87, "next_open": None, "next_close": 900}
    both = dict(p, open=True, next_open=None, next_close=1200)
    assert market_view(both, "best") == {"open": True, "payout": 0.87, "next_open": None, "next_close": 1200}
    shut = dict(p, digital_open=False, digital_next_open=300, digital_next_close=None)
    assert market_view(shut, "best") == {"open": False, "payout": None, "next_open": 300, "next_close": None}


# ---------------------------------------------------------------- adaptador da IQ

NOW = 1_794_170_124.5  # 20:35:24 UTC, segundo 24 da vela


class DigitalApi:
    """O pedaço da biblioteca que a digital usa: pedido de compra, resposta e avisos de posição."""

    def __init__(self, answer=21299005688, payouts=None):
        self.answer = answer
        self.placed = []
        self.api = SimpleNamespace(digital_option_placed_id={}, order_async={},
                                   place_digital_option_v2=self._place,
                                   top_assets_updated_data={"digital-option": [
                                       {"active_id": aid, "spot_profit": {"value": v, "is_valid": True}}
                                       for aid, v in (payouts or {81: 85}).items()]})

    def _place(self, instrument, active_id, amount):
        self.placed.append((instrument, active_id, amount))
        self.api.digital_option_placed_id["7"] = self.answer
        return "7"

    def get_server_timestamp(self):
        return NOW


def digital_broker(api, **digital):
    b = IQOptionBroker("a@b.c", "x", request_pause=0)
    b._api = api
    b._digital = {"GBPUSD-OTC": {"schedule": [(0, 4_000_000_000)], "enabled": True, "suspended": False, "label": "GBP/USD",
                                 "id": 81, "category": "Moedas"} | digital}
    return b


def test_compra_digital_com_vencimento_pelo_horario_da_iq():
    api = DigitalApi()
    b = digital_broker(api)
    assert b.payout_now("GBPUSD-OTC", DIGITAL) == 0.85 and b.tradable("GBPUSD-OTC", DIGITAL) == (True, "ok")
    t = b.buy("GBPUSD-OTC", "call", 1.0, kind=DIGITAL)
    assert api.placed == [("do81A20261108D203600T1MCSPT", 81, 1.0)]
    assert (t.order_id, t.kind, t.expires_at, t.opened_at) == (21299005688, DIGITAL, int(NOW // 60 + 1) * 60, NOW)


def test_digital_recusada_ou_fechada_nao_vira_ordem():
    refused = DigitalApi(answer={"code": "error_place_digital_order", "message": "saldo insuficiente"})
    with pytest.raises(BrokerError, match="recusou a ordem digital: saldo insuficiente"):
        digital_broker(refused).buy("GBPUSD-OTC", "put", 1.0, kind=DIGITAL)
    shut = DigitalApi()
    with pytest.raises(BrokerError, match="fechado para digital"):
        digital_broker(shut, suspended=True).buy("GBPUSD-OTC", "put", 1.0, kind=DIGITAL)
    with pytest.raises(BrokerError, match="não tem opção digital"):
        digital_broker(shut).buy("EURUSD-OTC", "put", 1.0, kind=DIGITAL)
    assert shut.placed == []


TURBO = {"id": 108, "kind": "turbo", "enabled": True, "suspended": False, "schedule": [(0, 4_000_000_000)], "payout": 0.84}
EURAUD_DIGITAL = {"schedule": [(0, 4_000_000_000)], "enabled": True, "suspended": False, "label": "EUR/AUD", "id": 108,
                  "category": "Moedas"}


def test_digital_do_mercado_normal_so_com_a_binaria_aberta():
    """09/11/2026: a IQ listava a digital -op aberta com a binária do par fechada e recusou todas ("invalid instrument")."""
    api = DigitalApi(payouts={81: 85, 108: 80})
    b = digital_broker(api)
    b._digital["EURAUD-op"] = dict(EURAUD_DIGITAL)
    ok, why = b.tradable("EURAUD-op", DIGITAL)  # só digital na lista, sem binária
    assert not ok and "só vale com a binária do par aberta" in why
    b._instruments = {"EURAUD-op": TURBO | {"enabled": False}}  # binária fechada
    assert not b.tradable("EURAUD-op", DIGITAL)[0]
    [p] = [p for p in b.pairs() if p["asset"] == "EURAUD-op"]
    assert not p["open"] and not p["digital_open"]  # para a troca de mercado, fechado: o par fica no OTC
    with pytest.raises(OrderRefused, match="só vale com a binária"):
        b.buy("EURAUD-op", "call", 1.0, kind=DIGITAL)
    assert api.placed == []
    b._instruments = {"EURAUD-op": dict(TURBO)}  # binária aberta: a digital vale
    assert b.tradable("EURAUD-op", DIGITAL) == (True, "ok")
    assert b.tradable("GBPUSD-OTC", DIGITAL) == (True, "ok")  # no OTC não tem essa regra


def test_par_que_a_iq_recusou_fica_sem_digital_por_um_tempo():
    api = DigitalApi(answer={"code": "error_place_digital_order", "message": "invalid instrument"})
    b = digital_broker(api)
    with pytest.raises(OrderRefused, match="recusou a ordem digital: invalid instrument"):
        b.buy("GBPUSD-OTC", "call", 1.0, kind=DIGITAL)
    ok, why = b.tradable("GBPUSD-OTC", DIGITAL)
    assert not ok and "recusou a digital de GBPUSD-OTC (invalid instrument)" in why
    [p] = [p for p in b.pairs() if p["asset"] == "GBPUSD-OTC"]
    assert not p["digital_open"] and "recusou" in p["digital_reason"]
    with pytest.raises(OrderRefused):  # não manda de novo
        b.buy("GBPUSD-OTC", "call", 1.0, kind=DIGITAL)
    assert len(api.placed) == 1
    api.get_server_timestamp = lambda: NOW + DIGITAL_REFUSED_SECONDS + 1  # passou o tempo: volta a tentar
    assert b.tradable("GBPUSD-OTC", DIGITAL) == (True, "ok")
    # Recusa que não é do par (saldo, valor): o par continua com digital
    poor = digital_broker(DigitalApi(answer={"code": "error_place_digital_order", "message": "saldo insuficiente"}))
    with pytest.raises(OrderRefused):
        poor.buy("GBPUSD-OTC", "call", 1.0, kind=DIGITAL)
    assert poor.tradable("GBPUSD-OTC", DIGITAL) == (True, "ok")


def closed_position(close_profit, invest=1, status="closed"):
    """Como a IQ manda (visto numa compra de US$ 1 na demo, perdida)."""
    return {"position-changed": {"name": "position-changed", "microserviceName": "portfolio", "msg": {
        "source": "digital-options", "instrument_type": "digital-option", "status": status, "invest": invest,
        "close_profit": close_profit if status == "closed" else None, "close_reason": "expired" if status == "closed" else None,
        "pnl_realized": (close_profit - invest) if status == "closed" else 0}}}


@pytest.mark.parametrize("back,expected", [(1.85, ("win", 0.85)), (0, ("loss", -1.0)), (1, ("empate", 0.0))])
def test_resultado_da_digital_pelo_aviso_de_posicao(back, expected):
    api = DigitalApi()
    api.api.order_async[555] = closed_position(back)
    r = digital_broker(api).order_result(OrderTicket(555, "GBPUSD-OTC", "call", 1.0, "PRACTICE", NOW, 60, kind=DIGITAL))
    assert (r.result, r.profit) == expected


def test_digital_aberta_ou_sem_aviso_nao_espera():
    api = DigitalApi()
    api.api.order_async[555] = closed_position(0, status="open")
    b = digital_broker(api)
    start = time.time()
    assert b.order_result(OrderTicket(555, "GBPUSD-OTC", "call", 1.0, "PRACTICE", NOW, 60, kind=DIGITAL)) is None
    assert b.order_result(OrderTicket(556, "GBPUSD-OTC", "call", 1.0, "PRACTICE", NOW, 60, kind=DIGITAL)) is None
    assert time.time() - start < 0.5


# ---------------------------------------------------------------- o bot

def digital_bot(tmp_path, option_type, binary=(True, "ok", 0.84), digital=(True, "ok", 0.87)):
    bot, broker, db, ap, nxt = approval_bot(tmp_path, mode="automatico")
    broker.offers = {BINARY: binary, DIGITAL: digital}
    bot.apply_config(bot.config.update({"option_type": option_type, "mode": "automatico"}))
    return bot, broker, db, ap, nxt


def test_maior_payout_manda_a_ordem_na_digital(tmp_path):
    bot, broker, db, ap, _ = digital_bot(tmp_path, "best")
    bot._poll(broker)  # confere o tipo (a Configuração mudou) e o preço toca o gatilho
    r = bot.runner()
    assert (r.kind, r.payout, r.payouts) == (DIGITAL, 0.87, {BINARY: 0.84, DIGITAL: 0.87})
    [t] = broker.tickets
    assert t.kind == DIGITAL and ap["status"] == "ordem enviada" and ap["kind"] == DIGITAL
    assert db.list_orders()[0]["option_type"] == DIGITAL
    snap = bot.snapshot()
    assert snap["option_type"] == "best" and snap["assets"][0]["kind"] == DIGITAL


def test_binaria_continua_o_padrao(tmp_path):
    bot, broker, db, _, _ = approval_bot(tmp_path, mode="automatico")
    broker.offers = {BINARY: (True, "ok", 0.84), DIGITAL: (True, "ok", 0.95)}
    assert bot.config.get().option_type == "binary"
    bot._poll(broker)
    assert [t.kind for t in broker.tickets] == [BINARY] and db.list_orders()[0]["option_type"] == BINARY


def test_digital_fechada_nao_manda_ordem_nem_troca_para_a_binaria(tmp_path):
    bot, broker, db, ap, _ = digital_bot(tmp_path, "digital", digital=(False, "EURUSD está fechado para digital agora", None))
    bot._poll(broker)
    assert not broker.tickets and ap["status"] == "bloqueada" and "fechado para digital" in ap["note"]
    assert bot.runner().tradable == (False, "EURUSD está fechado para digital agora")


def test_digital_com_payout_abaixo_do_minimo_nao_entra(tmp_path):
    bot, broker, db, ap, _ = digital_bot(tmp_path, "digital", digital=(True, "ok", 0.70))
    bot._poll(broker)
    assert not broker.tickets and ap["status"] == "bloqueada" and "payout de 70%" in ap["note"]


INVALID = "A IQ recusou a ordem digital: invalid instrument"


def test_maior_payout_vai_na_binaria_se_a_iq_recusar_a_digital(tmp_path):
    bot, broker, db, ap, _ = digital_bot(tmp_path, "best")
    broker.refuse_kinds = {DIGITAL: INVALID}
    bot._poll(broker)
    assert [t.kind for t in broker.tickets] == [BINARY] and ap["status"] == "ordem enviada"
    [o] = db.list_orders()
    assert o["option_type"] == BINARY and o["status"] not in ("erro", "bloqueada") and not o["error"]


def test_maior_payout_recusada_nos_dois_tipos_diz_o_motivo_de_cada(tmp_path):
    bot, broker, db, _, _ = digital_bot(tmp_path, "best")
    broker.refuse_kinds = {DIGITAL: INVALID, BINARY: "EURUSD está fechado para binária agora"}
    bot._poll(broker)
    [o] = db.list_orders()
    assert not broker.tickets and o["status"] == "erro" and o["option_type"] == DIGITAL
    assert o["error"] == INVALID + "; na binária: EURUSD está fechado para binária agora"
    assert bot.orders.snapshot()["open_orders"] == 0  # a vaga reservada volta


def test_digital_recusada_nao_troca_de_tipo_na_digital_fixa(tmp_path):
    bot, broker, db, _, _ = digital_bot(tmp_path, "digital")
    broker.refuse_kinds = {DIGITAL: INVALID}
    bot._poll(broker)
    [o] = db.list_orders()
    assert not broker.tickets and o["status"] == "erro" and o["error"] == INVALID


def test_maior_payout_nao_troca_para_binaria_abaixo_do_payout_minimo(tmp_path):
    bot, broker, db, _, _ = digital_bot(tmp_path, "best", binary=(True, "ok", 0.60))
    broker.refuse_kinds = {DIGITAL: INVALID}
    bot._poll(broker)
    [o] = db.list_orders()
    assert not broker.tickets and o["status"] == "erro" and o["error"] == INVALID


# ---------------------------------------------------------------- entrada manual e configuração

@pytest.fixture
def digital_client(manual_client):  # noqa: F811
    manual_client.broker.pair_list = [
        pair(digital=True, digital_open=True, digital_payout=0.87, digital_expiries=[1, 5]),
        pair("SODIGITAL-OTC", binary=False, open=False, payout=None, expiries=[], digital=True, digital_open=True,
             digital_payout=0.83, digital_expiries=[1, 5]),
        pair("DFECHADA-OTC", digital=True, digital_open=False, digital_reason="DFECHADA-OTC está fechado para digital agora",
             digital_expiries=[1, 5]),
    ]
    return manual_client


def test_entrada_manual_digital(digital_client):
    c = digital_client
    assert post(c, kind="digital", minutes=5).status_code == 200
    assert wait_for(lambda: len(c.broker.tickets) == 1)
    assert c.broker.tickets[0].kind == DIGITAL and c.broker.buy_minutes == [5]
    assert wait_for(lambda: c.get("/api/orders").json()[0]["option_type"] == "digital")
    assert post(c, asset="SODIGITAL-OTC", kind="digital").status_code == 200  # par só de digital


def test_entrada_manual_digital_recusa_o_que_a_iq_nao_aceita(digital_client):
    c = digital_client
    assert post(c, kind="digital", minutes=3).status_code == 422  # a digital só tem 1 e 5 min
    closed = post(c, asset="DFECHADA-OTC", kind="digital")
    assert closed.status_code == 422 and "fechado para digital" in closed.json()["detail"]
    only = post(c, asset="SODIGITAL-OTC")  # binária num par só de digital
    assert only.status_code == 422 and "só digital" in only.json()["detail"]
    assert post(c, kind="turbo").status_code == 422
    assert c.broker.tickets == []


def test_configuracao_tipo_de_opcao_e_ate_20_pares(tmp_path):
    assert UserConfig().option_type == "binary"
    assert UserConfig(option_type="best").option_type == "best"
    with pytest.raises(ValidationError):
        UserConfig(option_type="turbo")
    many = [f"PAR{i:02d}-OTC" for i in range(MAX_ASSETS)]
    assert MAX_ASSETS == 20 and UserConfig(assets=many).assets == many
    with pytest.raises(ValidationError, match="no máximo 20 pares"):
        UserConfig(assets=many + ["MAIS-OTC"])
    with make_client(tmp_path) as c:
        cfg = c.put("/api/config", json={"option_type": "digital", "assets": many}).json()
        assert (cfg["option_type"], cfg["max_assets"], len(cfg["assets"])) == ("digital", 20, 20)
        assert c.put("/api/config", json={"option_type": "outro"}).status_code == 422


def test_desempenho_separa_binaria_e_digital(tmp_path):
    with make_client(tmp_path) as c:
        db = c.app.state.db
        order(db, "win", amount=10, profit=8.4)
        order(db, "loss", amount=10, profit=-10)
        db.add_order(asset="EURUSD-OTC", timeframe=60, strategy="retracao_comando", direction="put", amount=10, account="REAL",
                     status="win", requested_at=T, profit=8.7, option_type="digital")
        st = c.get("/api/stats/orders?period=hoje&account=REAL").json()
        by_type = {g["key"]: (g["wins"], g["losses"]) for g in st["by_type"]}
        assert by_type == {"Binária": (1, 1), "Digital": (1, 0)}
