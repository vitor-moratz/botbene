"""Troca entre OTC e mercado normal, e o tipo de cada par (binária, digital) na lista da IQ."""

from types import SimpleNamespace

import pytest

from app.broker.base import BrokerError
from app.broker.iqoption import IQOptionBroker, _schedule_edges
from app.market.candle import twin_asset
from app.service.market import SWITCH_MARGIN_SECONDS, TO_NORMAL, TO_OTC, market_target
from tests.test_watch import WatchBroker
from tests.test_watchdog import candles, make, wait_for

NOW = 1_700_000_000
HOUR = 3600


def p(asset, open_=True, payout=0.85, next_open=None, next_close=None):
    return {"asset": asset, "label": asset, "category": "Moedas", "payout": payout, "open": open_, "reason": None if open_ else "fechado",
            "min": 1, "max": 20000, "expiries": [1, 2, 3, 4, 5], "next_open": next_open, "next_close": next_close}


def by_asset(*items):
    return {i["asset"]: i for i in items}


# ---------------------------------------------------------------- regra da troca

def test_par_gemeo():
    assert twin_asset("EURUSD-OTC") == "EURUSD-op"
    assert twin_asset("EURUSD-op") == "EURUSD-OTC"
    assert twin_asset("EURUSD") is None and twin_asset("BTCUSD-L") is None and twin_asset("-OTC") is None


def test_no_otc_vai_para_o_normal_quando_ele_abre():
    pairs = by_asset(p("EURUSD-OTC"), p("EURUSD-op"))
    assert market_target("EURUSD-OTC", pairs, NOW) == ("EURUSD-op", TO_NORMAL)


def test_no_otc_fica_com_o_normal_fechado_ou_sem_ele():
    assert market_target("EURUSD-OTC", by_asset(p("EURUSD-OTC"), p("EURUSD-op", open_=False)), NOW) is None
    assert market_target("AUDCAD-OTC", by_asset(p("AUDCAD-OTC")), NOW) is None
    assert market_target("EURUSD-OTC", {}, NOW) is None


def test_nao_vai_para_o_normal_que_fecha_logo():
    soon = by_asset(p("EURUSD-OTC"), p("EURUSD-op", next_close=NOW + SWITCH_MARGIN_SECONDS - 60))
    later = by_asset(p("EURUSD-OTC"), p("EURUSD-op", next_close=NOW + 5 * HOUR))
    assert market_target("EURUSD-OTC", soon, NOW) is None
    assert market_target("EURUSD-OTC", later, NOW) == ("EURUSD-op", TO_NORMAL)


def test_nao_vai_para_o_normal_com_payout_abaixo_do_minimo():
    pairs = by_asset(p("NZDUSD-OTC", payout=0.85), p("NZDUSD-op", payout=0.78))
    assert market_target("NZDUSD-OTC", pairs, NOW, min_payout=0.80) is None
    assert market_target("NZDUSD-OTC", pairs, NOW, min_payout=None) == ("NZDUSD-op", TO_NORMAL)
    assert market_target("NZDUSD-OTC", by_asset(p("NZDUSD-OTC"), p("NZDUSD-op", payout=0.80)), NOW, min_payout=0.80)


def test_no_normal_volta_para_o_otc_quando_ele_fecha():
    closed = by_asset(p("EURUSD-op", open_=False, next_open=NOW + 40 * HOUR), p("EURUSD-OTC"))
    assert market_target("EURUSD-op", closed, NOW) == ("EURUSD-OTC", TO_OTC)
    unknown = by_asset(p("EURUSD-op", open_=False), p("EURUSD-OTC"))  # sem horário de volta (suspenso)
    assert market_target("EURUSD-op", unknown, NOW) == ("EURUSD-OTC", TO_OTC)


def test_no_normal_fica_numa_pausa_curta_ou_com_o_otc_fechado():
    pause = by_asset(p("EURUSD-op", open_=False, next_open=NOW + 10 * 60), p("EURUSD-OTC"))
    assert market_target("EURUSD-op", pause, NOW) is None
    assert market_target("EURUSD-op", by_asset(p("EURUSD-op"), p("EURUSD-OTC")), NOW) is None
    otc_closed = by_asset(p("EURUSD-op", open_=False, next_open=NOW + 40 * HOUR), p("EURUSD-OTC", open_=False))
    assert market_target("EURUSD-op", otc_closed, NOW) is None


# ---------------------------------------------------------------- lista da IQ: horários e tipos

def test_proxima_abertura_e_fechamento_pela_grade():
    grid = [[NOW - HOUR, NOW + HOUR], [NOW + HOUR, NOW + 2 * HOUR], [NOW + 5 * HOUR, NOW + 6 * HOUR]]
    assert _schedule_edges(grid, NOW) == (None, NOW + 2 * HOUR)  # intervalos encostados contam como um só
    assert _schedule_edges(grid, NOW + 3 * HOUR) == (NOW + 5 * HOUR, None)
    assert _schedule_edges(grid, NOW + 7 * HOUR) == (None, None)
    assert _schedule_edges([], NOW) == (None, None)


def _instrument(**extra):
    return {"id": 1, "kind": "turbo", "enabled": True, "suspended": False, "schedule": [[0, 4_000_000_000]], "payout": 0.88,
            "label": "x", "category": "Moedas", "min": 2, "max": 20000, "count": 5} | extra


def _digital(open_=True, id_=None, category="Moedas"):
    return {"schedule": [(0, 4_000_000_000)] if open_ else [(NOW + HOUR, NOW + 2 * HOUR)], "enabled": True, "suspended": False,
            "label": "d", "id": id_, "category": category}


def _top_assets(payouts):
    """Mensagem "top-assets-updated" da digital, como a biblioteca guarda: {id: payout em %}."""
    return {"digital-option": [{"active_id": aid, "spot_profit": {"value": v, "is_valid": True}} for aid, v in payouts.items()]}


def iq_broker(instruments, digital=None, digital_payouts=None):
    broker = IQOptionBroker("a@b.c", "x")
    inner = SimpleNamespace(top_assets_updated_data=_top_assets(digital_payouts or {}))
    broker._api = SimpleNamespace(get_server_timestamp=lambda: NOW, api=inner)
    broker._instruments = instruments
    broker._digital = digital or {}
    return broker


def test_lista_diz_o_tipo_de_cada_par():
    broker = iq_broker(
        {"EURUSD-op": _instrument(), "EURUSD-OTC": _instrument(), "GBPUSD-op": _instrument(),
         "USDJPY-op": _instrument(schedule=[[NOW + 2 * HOUR, NOW + 9 * HOUR]])},
        {"EURUSD-op": _digital(id_=1861), "EURUSD-OTC": _digital(open_=False, id_=76), "XAUUSD": _digital(id_=74, category="Outros"),
         "USDJPY-OTC": _digital(id_=85)},
        {1861: 87, 76: 86, 74: 80, 85: 83})
    pairs = {x["asset"]: x for x in broker.pairs()}
    assert sorted(pairs) == ["EURUSD-OTC", "EURUSD-op", "GBPUSD-op", "USDJPY-OTC", "USDJPY-op", "XAUUSD"]
    eur = pairs["EURUSD-op"]
    assert (eur["binary"], eur["digital"], eur["digital_open"], eur["digital_payout"]) == (True, True, True, 0.87)
    assert eur["digital_expiries"] == [1, 5] and eur["digital_next_close"] == 4_000_000_000
    otc = pairs["EURUSD-OTC"]
    assert (otc["digital"], otc["digital_open"], otc["digital_next_open"]) == (True, False, NOW + HOUR)
    assert "fechado para digital" in otc["digital_reason"]
    assert (pairs["GBPUSD-op"]["digital"], pairs["GBPUSD-op"]["digital_open"]) == (False, False)
    only = pairs["XAUUSD"]  # só digital, no mercado normal: sem binária aberta a IQ recusa a digital
    assert (only["binary"], only["digital"], only["open"], only["expiries"]) == (False, True, False, [])
    assert (only["digital_open"], only["digital_payout"], only["category"]) == (False, 0.80, "Outros")
    assert "só digital" in only["reason"] and "só vale com a binária" in only["digital_reason"]
    otc_only = pairs["USDJPY-OTC"]  # só digital no OTC: o bot opera com "Digital" ou "A de maior payout"
    assert (otc_only["binary"], otc_only["digital_open"], otc_only["digital_payout"]) == (False, True, 0.83)
    assert otc_only["category"] == "Moedas"  # mesma categoria do par de binária com o mesmo nome
    assert (pairs["USDJPY-op"]["open"], pairs["USDJPY-op"]["next_open"], pairs["USDJPY-op"]["next_close"]) == (False, NOW + 2 * HOUR, None)
    assert pairs["EURUSD-op"]["next_close"] == 4_000_000_000 and pairs["EURUSD-op"]["next_open"] is None


def test_digital_sem_payout_conta_como_fechada():
    broker = iq_broker({"EURUSD-OTC": _instrument()}, {"EURUSD-OTC": _digital(id_=76)}, {76: 0})  # payout zero na IQ
    [pair] = broker.pairs()
    assert (pair["digital"], pair["digital_open"], pair["digital_payout"]) == (True, False, None)
    assert broker.tradable("EURUSD-OTC", "digital") == (False, "EURUSD-OTC: payout da digital indisponível agora")
    assert broker.tradable("EURUSD-OTC") == (True, "ok")  # a binária continua


def test_payout_da_digital_velho_demais_vira_desconhecido(monkeypatch):
    broker = iq_broker({}, {"EURUSD-OTC": _digital(id_=76)}, {76: 88})
    assert broker.payout_now("EURUSD-OTC", "digital") == 0.88
    assert broker.payout_now("EURUSD-OTC") is None  # binária: não está na lista
    import app.broker.iqoption as iq
    monkeypatch.setattr(iq.time, "monotonic", lambda: broker._dp_seen + iq.DIGITAL_PAYOUT_DEAD + 1)
    assert broker.payout_now("EURUSD-OTC", "digital") is None
    assert broker.tradable("EURUSD-OTC", "digital")[0] is False


def test_sem_a_lista_de_digitais_nao_diz_nada_sobre_digital():
    pairs = iq_broker({"EURUSD-op": _instrument()}).pairs()
    assert [(x["asset"], x["digital"], x["digital_open"]) for x in pairs] == [("EURUSD-op", None, None)]


def test_par_desligado_pela_iq_nao_tem_horario_de_volta():
    pairs = iq_broker({"EURUSD-op": _instrument(enabled=False)}).pairs()
    assert (pairs[0]["open"], pairs[0]["next_open"], pairs[0]["next_close"]) == (False, None, None)


def test_binaria_desligada_no_fim_de_semana_diz_quando_o_normal_abre():
    """Como a IQ manda no domingo: binária -op desligada, mas com a grade da semana (abre 23:00)."""
    weekend = [[NOW + 2 * HOUR, NOW + 19 * HOUR]]
    broker = iq_broker({"EURUSD-op": _instrument(enabled=False, schedule=weekend),
                        "USDCHF-op": _instrument(enabled=False, suspended=True, schedule=weekend)},
                       {"EURUSD-op": _digital(open_=False, id_=1861)}, {1861: 85})
    pairs = {x["asset"]: x for x in broker.pairs()}
    eur = pairs["EURUSD-op"]
    assert (eur["open"], eur["next_open"], eur["digital_open"], eur["digital_next_open"]) == (False, NOW + 2 * HOUR, False, NOW + HOUR)
    assert pairs["USDCHF-op"]["next_open"] is None  # suspenso: sem horário de volta


def _digital_api(answer):
    inner = SimpleNamespace(underlying_list_data=None, sent=[])

    def send(name, msg, request_id=""):
        inner.sent.append(msg)
        inner.underlying_list_data = answer

    inner.send_websocket_request = send
    return SimpleNamespace(api=inner)


def test_le_a_lista_de_digitais_pelo_pedido_novo_sem_o_laco_da_biblioteca():
    from iqoptionapi import constants as op_code

    broker = IQOptionBroker("a@b.c", "x")
    broker._api = _digital_api({"underlying": [
        {"underlying": "EURUSD-op", "name": "EUR/USD", "active_id": 1861, "active_type": "Forex",
         "schedule": [{"open": 1, "close": 2}], "is_suspended": False},
        {"underlying": "eurusd-otc", "schedule": []},
        {"underlying": "TESTNOK-OTC", "active_id": 987654, "active_type": "Forex", "schedule": []},
        {"underlying": "GER30/UK100", "schedule": []},  # nome que o bot não aceita
        "lixo",
    ]})
    try:
        broker._load_digital()
        assert broker._api.api.sent[0]["name"] == "digital-option-instruments.get-underlying-list"
        assert sorted(broker._digital) == ["EURUSD-OTC", "EURUSD-op", "TESTNOK-OTC"]
        assert broker._digital["EURUSD-op"] == {"schedule": [(1.0, 2.0)], "enabled": True, "suspended": False, "label": "EUR/USD",
                                                "id": 1861, "category": "Moedas"}
        assert op_code.ACTIVES["TESTNOK-OTC"] == 987654  # par só de digital: o id serve para velas e stream
    finally:
        op_code.ACTIVES.pop("TESTNOK-OTC", None)


def test_formato_desconhecido_ou_sem_resposta_nao_apaga_a_lista():
    broker = IQOptionBroker("a@b.c", "x")
    broker._digital = {"EURUSD": _digital()}
    broker._api = _digital_api({"underlying": [{"outro": "formato"}]})
    broker._load_digital()
    broker._api = _digital_api({"erro": True})
    broker._load_digital()
    broker._api = _digital_api({"underlying": {"EURUSD": "não é lista"}})
    broker._load_digital()
    assert list(broker._digital) == ["EURUSD"]


def test_resposta_estranha_nao_derruba_a_atualizacao_e_espera_para_tentar_de_novo():
    broker = IQOptionBroker("a@b.c", "x")
    broker._api = _digital_api({"underlying": [{"underlying": "EURUSD", "schedule": [{"open": "x", "close": 2}]}]})
    broker._load_digital()  # float("x") falha: vira aviso no log, sem exceção
    assert broker._digital == {} and broker._digital_retry_at > 0
    broker._load_digital()
    assert len(broker._api.api.sent) == 1  # dentro da espera, nem pede


# ---------------------------------------------------------------- o bot troca

class MarketBroker(WatchBroker):
    """Lista de pares mutável; o histórico de alguns pares pode falhar."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fail_assets: set[str] = set()

    def get_candles(self, asset, timeframe, count, end_ts=None):
        if asset in self.fail_assets:
            raise BrokerError(f"Nenhuma vela recebida para {asset}")
        return super().get_candles(asset, timeframe, count, end_ts)


def market_bot(tmp_path, pair_list, n_live=4, auto=True):
    history, live = candles(n_live=n_live)
    broker = MarketBroker(history, list(live))
    broker.pair_list = pair_list
    bot, db, _ = make(tmp_path, [broker], assets=("EURUSD-OTC",))
    bot.config.update({"strategies": {}, "auto_market": auto})  # sem entrada armada para segurar a troca
    bot.apply_config(bot.config.get())
    bot.poll_seconds = 0.01
    bot.clock_stall_seconds = bot.stall_seconds = 1000
    bot.market_check_seconds = 0.01
    bot.switch_window = (0, 0)  # o relógio da corretora falsa fica parado no começo da vela
    return bot, broker, db


@pytest.fixture
def stop_after():
    bots = []
    yield bots.append
    for bot in bots:
        bot.stop()
        bot.watcher.stop()


def test_ao_iniciar_ja_comeca_no_mercado_aberto(tmp_path, stop_after):
    bot, broker, _ = market_bot(tmp_path, [p("EURUSD-OTC"), p("EURUSD-op"), p("GBPUSD-OTC"), p("GBPUSD-op", open_=False)])
    stop_after(bot)
    bot.start(["EURUSD-OTC", "GBPUSD-OTC"], 60)
    assert wait_for(lambda: bot.status == "rodando")
    assert list(bot.runners) == ["EURUSD-op", "GBPUSD-OTC"]
    assert bot.focus == "EURUSD-op"
    snap = bot.snapshot()
    assert snap["auto_market"] is True
    assert [(s["from"], s["to"], s["reason"]) for s in snap["market_swaps"]] == [("EURUSD-OTC", "EURUSD-op", "mercado normal aberto")]


def test_com_a_troca_desligada_fica_no_otc(tmp_path, stop_after):
    bot, _, _ = market_bot(tmp_path, [p("EURUSD-OTC"), p("EURUSD-op")], auto=False)
    stop_after(bot)
    bot.start(["EURUSD-OTC"], 60)
    assert wait_for(lambda: bot.status == "rodando")
    assert list(bot.runners) == ["EURUSD-OTC"] and bot.snapshot()["market_swaps"] == []


def test_rodando_troca_quando_o_mercado_normal_abre(tmp_path, stop_after):
    bot, broker, db = market_bot(tmp_path, [p("EURUSD-OTC"), p("EURUSD-op", open_=False)])
    stop_after(bot)
    events = []
    publish = bot.hub.publish
    bot.hub.publish = lambda e: (events.append(e), publish(e))[1]
    bot.start(["EURUSD-OTC"], 60)
    assert wait_for(lambda: bot.status == "rodando")
    old_session = bot.runners["EURUSD-OTC"].session_id
    broker.pair_list = [p("EURUSD-OTC"), p("EURUSD-op")]
    assert wait_for(lambda: list(bot.runners) == ["EURUSD-op"])
    new = bot.runners["EURUSD-op"]
    assert new.ready and new.session_id not in (None, old_session)
    assert bot.focus == "EURUSD-op" and bot.status == "rodando"
    assert wait_for(lambda: broker.released == ["EURUSD-OTC"])  # o stream do OTC é cancelado logo depois da troca
    assert "EURUSD-op" in broker.streams_started
    assert any(e["type"] == "reload" for e in events)
    assert bot.snapshot()["market_swaps"][0]["reason"] == "mercado normal abriu"
    from app.db.models import SessionRow
    with db.Session() as s:
        assert "trocou para EURUSD-op" in s.get(SessionRow, old_session).stop_reason
    # e volta para o OTC quando o normal fecha
    broker.pair_list = [p("EURUSD-OTC"), p("EURUSD-op", open_=False, next_open=NOW + 40 * HOUR)]
    assert wait_for(lambda: list(bot.runners) == ["EURUSD-OTC"])
    assert bot.snapshot()["market_swaps"][0]["reason"] == "mercado normal fechou"


def test_par_novo_que_nao_carrega_mantem_o_antigo(tmp_path, stop_after):
    bot, broker, _ = market_bot(tmp_path, [p("EURUSD-OTC"), p("EURUSD-op", open_=False)])
    stop_after(bot)
    broker.fail_assets = {"EURUSD-op"}
    bot.start(["EURUSD-OTC"], 60)
    assert wait_for(lambda: bot.status == "rodando")
    broker.pair_list = [p("EURUSD-OTC"), p("EURUSD-op")]
    assert wait_for(lambda: "EURUSD-op" in bot._switch_retry)
    assert list(bot.runners) == ["EURUSD-OTC"] and bot.runners["EURUSD-OTC"].ready
    assert bot.status == "rodando" and bot.progress is None
    assert broker.released == []  # o OTC continua com o stream
    summary = bot.snapshot()["assets"][0]
    assert summary["switch_to"] == "EURUSD-op" and "não carregou" in summary["switch_wait"]


def test_erro_inesperado_na_troca_nao_para_o_bot(tmp_path, stop_after):
    bot, broker, _ = market_bot(tmp_path, [p("EURUSD-OTC"), p("EURUSD-op", open_=False)])
    stop_after(bot)
    bot.start(["EURUSD-OTC"], 60)
    assert wait_for(lambda: bot.status == "rodando")
    calls = []

    def broken():
        calls.append(1)
        raise RuntimeError("bug")

    broker.pairs = broken
    assert wait_for(lambda: calls)
    assert bot.status == "rodando" and bot.error is None
    assert bot._next_market_check > 0


def test_troca_espera_entrada_armada_pedido_aberto_e_o_meio_da_vela(tmp_path):
    bot, broker, _ = market_bot(tmp_path, [])
    bot._bootstrap(broker)
    r = bot.runners["EURUSD-OTC"]
    r.armed = []
    bot.switch_window = (18, 25)
    base = 1_700_000_040  # começo de uma vela de 1 min
    assert bot._switch_wait(r, base + 5) == "esperando o meio da vela"
    assert bot._switch_wait(r, base + 50) == "esperando o meio da vela"
    assert bot._switch_wait(r, base + 20) is None
    r.armed = [object()]
    assert "armada" in bot._switch_wait(r, base + 20)
    r.armed = []
    bot.approvals = [{"asset": "EURUSD-OTC", "status": "aprovado"}]
    assert "pedido" in bot._switch_wait(r, base + 20)
    bot.approvals = [{"asset": "EURUSD-OTC", "status": "ordem enviada"}]
    assert bot._switch_wait(r, base + 20) is None


def test_troca_ligada_por_padrao_e_desligada_pela_tela(tmp_path):
    from tests.test_config import make_client

    with make_client(tmp_path) as client:
        assert client.get("/api/config").json()["auto_market"] is True
        assert client.get("/api/status").json()["auto_market"] is True
        assert client.put("/api/config", json={"auto_market": False}).json()["auto_market"] is False
        assert client.get("/api/status").json()["auto_market"] is False


# ---------------------------------------------------------------- "normal primeiro" (09/11/2026)

from app.service.market import market_targets, normal_first_targets  # noqa: E402

TWO_OTC = ["EURUSD-OTC", "GBPUSD-OTC"]
TWO_OP = ["EURUSD-op", "GBPUSD-op"]


def test_normal_primeiro_com_um_normal_aberto_todos_vao_para_o_normal():
    pairs = by_asset(p("EURUSD-OTC"), p("EURUSD-op"), p("GBPUSD-OTC"), p("GBPUSD-op", open_=False))
    got = normal_first_targets(TWO_OTC, pairs, NOW)
    assert got == {"EURUSD-OTC": ("EURUSD-op", TO_NORMAL), "GBPUSD-OTC": ("GBPUSD-op", TO_NORMAL)}  # o fechado espera no normal
    assert normal_first_targets(TWO_OP, pairs, NOW) == {"EURUSD-op": None, "GBPUSD-op": None}


def test_normal_primeiro_so_vai_para_o_otc_quando_todos_fecham():
    closed = by_asset(p("EURUSD-OTC"), p("EURUSD-op", open_=False), p("GBPUSD-OTC"), p("GBPUSD-op", open_=False))
    assert normal_first_targets(TWO_OP, closed, NOW) == {"EURUSD-op": ("EURUSD-OTC", TO_OTC), "GBPUSD-op": ("GBPUSD-OTC", TO_OTC)}
    soon = by_asset(p("EURUSD-OTC"), p("EURUSD-op", open_=False, next_open=NOW + 10 * 60), p("GBPUSD-OTC"),
                    p("GBPUSD-op", open_=False))
    assert normal_first_targets(TWO_OP, soon, NOW) == {"EURUSD-op": None, "GBPUSD-op": None}  # um reabre logo: espera


def test_normal_primeiro_nao_conta_normal_que_fecha_logo_ou_paga_pouco():
    closing = by_asset(p("EURUSD-OTC"), p("EURUSD-op", next_close=NOW + 10 * 60), p("GBPUSD-OTC"), p("GBPUSD-op", open_=False))
    assert normal_first_targets(TWO_OP, closing, NOW)["GBPUSD-op"] == ("GBPUSD-OTC", TO_OTC)
    low = by_asset(p("EURUSD-OTC"), p("EURUSD-op", payout=0.70), p("GBPUSD-OTC"), p("GBPUSD-op", open_=False))
    assert normal_first_targets(TWO_OP, low, NOW, min_payout=0.80)["EURUSD-op"] == ("EURUSD-OTC", TO_OTC)


def test_cada_par_sozinho_continua_igual():
    pairs = by_asset(p("EURUSD-OTC"), p("EURUSD-op"), p("GBPUSD-OTC"), p("GBPUSD-op", open_=False))
    assert market_targets(TWO_OTC, pairs, NOW) == {a: market_target(a, pairs, NOW) for a in TWO_OTC}
    assert market_targets(TWO_OTC, pairs, NOW)["GBPUSD-OTC"] is None  # par a par: o fechado fica no OTC


def test_normal_primeiro_no_bot(tmp_path, stop_after):
    bot, broker, _ = market_bot(tmp_path, [p("EURUSD-OTC"), p("EURUSD-op"), p("GBPUSD-OTC"), p("GBPUSD-op", open_=False)])
    bot.config.update({"market_mode": "normal_primeiro"})
    bot.apply_config(bot.config.get())
    stop_after(bot)
    bot.start(TWO_OTC, 60)
    assert wait_for(lambda: bot.status == "rodando")
    assert sorted(bot.runners) == TWO_OP  # GBPUSD fica no normal fechado, esperando
    snap = bot.snapshot()
    assert snap["market_mode"] == "normal_primeiro"
    assert {s["reason"] for s in snap["market_swaps"]} == {"normal primeiro: há par normal aberto"}
    broker.pair_list = [p("EURUSD-OTC"), p("EURUSD-op", open_=False), p("GBPUSD-OTC"), p("GBPUSD-op", open_=False)]
    assert wait_for(lambda: sorted(bot.runners) == TWO_OTC)  # todos os normais fecharam: tudo para o OTC
    assert bot.snapshot()["market_swaps"][0]["reason"] == "normal primeiro: todos os pares normais fecharam"


def test_jeito_da_troca_na_configuracao(tmp_path):
    from tests.test_config import make_client
    with make_client(tmp_path) as client:
        assert client.get("/api/config").json()["market_mode"] == "por_par"
        r = client.put("/api/config", json={"market_mode": "normal_primeiro"})
        assert r.status_code == 200 and r.json()["market_mode"] == "normal_primeiro"
        assert client.put("/api/config", json={"market_mode": "outro"}).status_code == 422
