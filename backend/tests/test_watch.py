"""Observador: gráfico ao vivo de qualquer par, com o bot parado ou em par fora da lista dele."""

import threading
import time

import pytest

from app.broker.base import BrokerError
from app.broker.iqoption import IQOptionBroker
from tests.test_watchdog import FlakyBroker, candles, make, wait_for


class WatchBroker(FlakyBroker):
    """Registra o que foi cancelado e devolve as velas ao vivo uma a uma."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.released: list[str] = []

    def release_stream(self, asset, timeframe):
        self.released.append(asset)


def watcher_bot(tmp_path, broker, assets=("EURUSD",)):
    bot, db, made = make(tmp_path, [broker], assets=assets)
    bot.poll_seconds = 0.01
    bot.clock_stall_seconds = bot.stall_seconds = 1000
    bot.watcher.poll_seconds, bot.watcher.retry_seconds = 0.01, 0.01
    return bot, db, made


def signals_of(db):
    return db.list_signals(limit=5000)


@pytest.fixture
def bot_and_broker(tmp_path):
    history, live = candles(n_live=6)
    broker = WatchBroker(history, list(live))
    bot, db, made = watcher_bot(tmp_path, broker)
    yield bot, broker, db, made
    bot.stop()
    bot.watcher.stop()


def test_com_o_bot_parado_o_par_da_tela_fica_ao_vivo(bot_and_broker):
    bot, broker, db, _ = bot_and_broker
    events = []
    publish = bot.hub.publish
    bot.hub.publish = lambda e: (events.append(e), publish(e))[1]
    bot.set_focus("EURUSD")
    assert wait_for(lambda: bot.snapshot()["watch"] and bot.snapshot()["watch"]["state"] == "ao_vivo")
    assert wait_for(lambda: not broker.live)  # consumiu as velas ao vivo
    assert broker.streams_started == ["EURUSD"]
    snap = bot.snapshot()
    assert snap["status"] == "parado" and snap["asset"] == "EURUSD" and snap["forming"] is not None
    assert bot.chart(100)["forming"] is not None
    assert any(e["type"] == "tick" for e in events) and any(e["type"] == "closed" for e in events)
    assert signals_of(db) == []  # só alimenta o gráfico


def test_guarda_as_velas_que_fecham_e_a_moeda_da_conta(bot_and_broker):
    bot, broker, db, _ = bot_and_broker
    broker.currency = lambda: "BRL"
    bot.set_focus("EURUSD")
    closed_before = broker.history[-1].ts
    assert wait_for(lambda: not broker.live)
    assert wait_for(lambda: db.load_candles("EURUSD", 60, 2000)[-1].ts > closed_before)
    assert bot.currency == "BRL"


def test_par_fora_da_lista_do_bot_nao_atrapalha_o_bot(tmp_path):
    history, live = candles(n_live=4)
    broker = WatchBroker(history, list(live))
    bot, db, _ = watcher_bot(tmp_path, broker)
    bot.start(["EURUSD"], 60)
    try:
        assert wait_for(lambda: bot.status == "rodando")
        bot.set_focus("GBPUSD")
        assert wait_for(lambda: bot.snapshot()["watch"] and bot.snapshot()["watch"]["state"] == "ao_vivo")
        assert bot.focus == "GBPUSD" and bot.chart(50)["asset"] == "GBPUSD"
        assert [a["asset"] for a in bot.snapshot()["assets"]] == ["EURUSD"]  # olhar não muda o que o bot opera
        bot.set_focus("EURUSD")
        assert wait_for(lambda: bot.snapshot()["watch"] is None)
        assert wait_for(lambda: broker.released == ["GBPUSD"])  # cancelou só o stream do par que saiu
        assert bot.runner() is bot.runners["EURUSD"]
    finally:
        bot.stop()


def test_iniciar_o_bot_continua_no_par_da_tela_e_assume_o_stream(tmp_path):
    history, live = candles(n_live=4)
    broker = WatchBroker(history, list(live))
    bot, _, _ = watcher_bot(tmp_path, broker)
    bot.set_focus("EURUSD")
    assert wait_for(lambda: broker.streams_started == ["EURUSD"])
    bot.start(["EURUSD", "GBPUSD"], 60)
    try:
        assert wait_for(lambda: bot.status == "rodando")
        assert wait_for(lambda: bot.watcher.asset is None)  # o bot assumiu o par
        assert bot.focus == "EURUSD"
        assert broker.released == []  # o stream agora é do bot
    finally:
        bot.stop()


def test_iniciar_o_bot_nao_tira_da_tela_um_par_fora_da_lista(tmp_path):
    history, live = candles(n_live=2)
    broker = WatchBroker(history, list(live))
    bot, _, _ = watcher_bot(tmp_path, broker)
    bot.set_focus("USDJPY")
    assert wait_for(lambda: broker.streams_started == ["USDJPY"])
    bot.start(["EURUSD"], 60)
    try:
        assert wait_for(lambda: bot.status == "rodando")
        assert bot.focus == "USDJPY" and bot.watcher.asset == "USDJPY"
    finally:
        bot.stop()
        bot.watcher.stop()


def test_ao_parar_com_painel_aberto_o_grafico_continua_ao_vivo(tmp_path, monkeypatch):
    history, live = candles(n_live=2)
    broker = WatchBroker(history, list(live))
    bot, _, _ = watcher_bot(tmp_path, broker)
    bot.start(["EURUSD"], 60)
    assert wait_for(lambda: bot.status == "rodando")
    monkeypatch.setattr(type(bot.hub), "clients", property(lambda self: 1))
    bot.stop()
    try:
        assert bot.status == "parado"
        assert wait_for(lambda: bot.watcher.asset == "EURUSD")
        assert wait_for(lambda: bot.snapshot()["watch"]["state"] == "ao_vivo")
    finally:
        bot.watcher.stop()


def test_ao_parar_sem_painel_o_observador_nao_liga(tmp_path):
    history, live = candles(n_live=2)
    bot, _, _ = watcher_bot(tmp_path, WatchBroker(history, list(live)))
    bot.start(["EURUSD"], 60)
    assert wait_for(lambda: bot.status == "rodando")
    bot.stop()
    assert bot.watcher.asset is None


def test_troca_rapida_abandona_o_par_anterior(tmp_path):
    history, live = candles(n_live=2)
    broker = WatchBroker(history, list(live))
    gate, reached = threading.Event(), threading.Event()
    real_get = broker.get_candles
    asked = []

    def slow_get(asset, timeframe, count, end_ts=None):
        asked.append(asset)
        if asset == "EURUSD":
            reached.set()
            gate.wait(5)
        return real_get(asset, timeframe, count, end_ts)

    broker.get_candles = slow_get
    bot, _, _ = watcher_bot(tmp_path, broker)
    bot.set_focus("EURUSD")
    assert reached.wait(5)
    bot.set_focus("GBPUSD")
    assert wait_for(lambda: broker.streams_started == ["GBPUSD"])
    gate.set()
    time.sleep(0.1)
    assert broker.streams_started == ["GBPUSD"]  # o par abandonado não abriu stream
    assert bot.snapshot()["asset"] == "GBPUSD"
    bot.watcher.stop()


def test_voltar_ao_mesmo_par_nao_cancela_o_stream_novo(tmp_path):
    history, live = candles(n_live=2)
    broker = WatchBroker(history, list(live))
    bot, _, _ = watcher_bot(tmp_path, broker)
    bot.set_focus("EURUSD")
    assert wait_for(lambda: broker.streams_started == ["EURUSD"])
    first = bot.watcher._watch
    first.cancel.set()  # o velho ainda vai terminar...
    bot.watcher._watch = None
    bot.set_focus("EURUSD")  # ...e o novo já está no mesmo par
    assert wait_for(lambda: broker.streams_started == ["EURUSD", "EURUSD"])
    first.thread.join(2)
    assert broker.released == []
    bot.watcher.stop()


def test_trocar_de_par_nao_repete_o_mesmo_observador(bot_and_broker):
    bot, broker, _, _ = bot_and_broker
    bot.set_focus("EURUSD")
    assert wait_for(lambda: broker.streams_started == ["EURUSD"])
    w = bot.watcher._watch
    bot.set_focus("EURUSD")
    assert bot.watcher._watch is w and broker.streams_started == ["EURUSD"]


def test_conexao_que_cai_carrega_tudo_de_novo(tmp_path):
    history, live = candles(n_live=2)
    first, second = WatchBroker(history, list(live)), WatchBroker(history, [])
    bot, _, made = make(tmp_path, [first, second])
    bot.watcher.poll_seconds, bot.watcher.retry_seconds = 0.01, 0.01
    bot.set_focus("EURUSD")
    assert wait_for(lambda: first.streams_started == ["EURUSD"])
    bot._drop_broker()  # ex.: trocou de login
    assert wait_for(lambda: second.streams_started == ["EURUSD"])
    assert made == [first, second]
    assert wait_for(lambda: bot.snapshot()["watch"]["state"] == "ao_vivo")
    bot.watcher.stop()


def test_sem_conexao_avisa_e_tenta_de_novo(tmp_path):
    history, live = candles(n_live=2)
    ok = WatchBroker(history, list(live))
    bot, _, _ = make(tmp_path, [BrokerError("sem internet"), ok])
    bot.watcher.poll_seconds, bot.watcher.retry_seconds = 0.01, 0.01
    import app.service.bot as bot_module

    bot_module.CONNECT_BACKOFF_SECONDS, saved = 0, bot_module.CONNECT_BACKOFF_SECONDS
    try:
        states = []
        publish = bot.hub.publish

        def spy(event):
            if event["type"] == "status" and event["watch"]:
                states.append(event["watch"]["state"])
            publish(event)

        bot.hub.publish = spy
        bot.set_focus("EURUSD")
        assert wait_for(lambda: bot.snapshot()["watch"] and bot.snapshot()["watch"]["state"] == "ao_vivo")
        assert "sem_conexao" in states
    finally:
        bot_module.CONNECT_BACKOFF_SECONDS = saved
        bot.watcher.stop()


def test_durante_a_reconexao_do_bot_nao_abre_outro_login(tmp_path):
    history, live = candles(n_live=2)
    broker = WatchBroker(history, list(live))
    logins = []

    def factory():
        logins.append(1)
        return broker

    bot, _, _ = make(tmp_path, [broker])
    bot._broker_factory = factory
    bot.watcher.poll_seconds, bot.watcher.retry_seconds = 0.01, 0.01
    bot.status = "reconectando"
    bot.set_focus("EURUSD")
    time.sleep(0.1)
    assert logins == [] and broker.streams_started == []
    assert bot.snapshot()["watch"]["state"] == "sem_conexao"
    bot.status = "parado"
    assert wait_for(lambda: broker.streams_started == ["EURUSD"])
    assert logins == [1]
    bot.watcher.stop()


def test_sem_painel_por_um_tempo_para_sozinho(tmp_path):
    history, live = candles(n_live=2)
    broker = WatchBroker(history, list(live))
    bot, _, _ = watcher_bot(tmp_path, broker)
    bot.watcher.idle_seconds = 0.05
    bot.set_focus("EURUSD")
    assert wait_for(lambda: bot.watcher.asset is None)
    assert broker.released in ([], ["EURUSD"])  # cancela se já tinha aberto o stream
    assert bot.snapshot()["watch"] is None


def test_par_fechado_mostra_o_historico_com_o_motivo(tmp_path):
    history, live = candles(n_live=2)
    broker = WatchBroker(history, list(live))
    broker.tradable = lambda asset: (False, f"{asset} está fechado para binária agora")
    bot, _, _ = watcher_bot(tmp_path, broker)
    bot.set_focus("EURUSD")
    assert wait_for(lambda: bot.runner() is not None and bot.runner().ready)
    assert bot.runner().tradable == (False, "EURUSD está fechado para binária agora")
    assert bot.chart(50)["candles"]
    bot.watcher.stop()


# ---------------------------------------------------------------- lista de pares da IQ

def _instrument(**extra):
    return {"id": 1, "kind": "turbo", "enabled": True, "suspended": False, "schedule": [[0, 4_000_000_000]], "payout": 0.88,
            "label": "EUR/USD (OTC)", "category": "Moedas", "min": 2, "max": 20000, "count": 5} | extra


def test_iq_lista_os_pares_com_limites_e_expiracoes():
    from types import SimpleNamespace

    broker = IQOptionBroker("a@b.c", "x")
    broker._api = SimpleNamespace(get_server_timestamp=lambda: 1_000_000)
    broker._instruments = {
        "EURUSD-OTC": _instrument(),
        "EURUSD-op": _instrument(count=10, payout=0.84),  # a IQ diz 10, mas acima de 5 min não é este produto
        "UM-OTC": _instrument(count=1),
        "FECHADO-OTC": _instrument(enabled=False),
        "SO15MIN-OTC": _instrument(kind="binary"),
        "GER30/UK100-OTC": _instrument(),
        "JAPAN225:N": _instrument(),
        "European AI": _instrument(),
        "OpenAI-OTC": _instrument(),
    }
    pairs = {p["asset"]: p for p in broker.pairs()}
    assert sorted(pairs) == ["EURUSD-OTC", "EURUSD-op", "FECHADO-OTC", "UM-OTC"]
    assert pairs["EURUSD-OTC"] == {"asset": "EURUSD-OTC", "label": "EUR/USD (OTC)", "category": "Moedas", "payout": 0.88, "open": True,
                                   "reason": None, "min": 2, "max": 20000, "expiries": [1, 2, 3, 4, 5],
                                   "market": "otc", "binary": True, "digital": None, "digital_open": None,
                                   "digital_payout": None, "digital_reason": None, "digital_expiries": [],
                                   "digital_next_open": None, "digital_next_close": None,
                                   "next_open": None, "next_close": 4_000_000_000}
    assert pairs["EURUSD-op"]["market"] == "normal"
    assert pairs["EURUSD-op"]["expiries"] == [1, 2, 3, 4, 5]
    assert pairs["UM-OTC"]["expiries"] == [1]
    assert pairs["FECHADO-OTC"]["open"] is False and "fechado" in pairs["FECHADO-OTC"]["reason"]


def test_iq_guarda_categoria_limites_e_nome_ao_ler_a_lista():
    from types import SimpleNamespace

    init = {"groups": {"1": "front.forex", "16": "front.crypto currencies", "9": "front.outra coisa"}, "turbo": {"actives": {
        "76": {"name": "front.EURUSD-OTC", "description": "front.EUR/USD (OTC)", "group_id": 1, "enabled": True, "is_suspended": False,
               "schedule": [], "minimal_bet": 2, "maximal_bet": 20000, "option": {"profit": {"commission": 12}, "count": 5}},
        "77": {"name": "front.BTCUSD-OTC", "group_id": 16, "option": {}},
        "78": {"name": "front.XYZ-OTC", "group_id": 9, "option": {}},
    }}}
    broker = IQOptionBroker("a@b.c", "x")
    broker._api = SimpleNamespace(get_all_init_v2=lambda: init)
    broker._load_instruments()
    info = broker._instruments["EURUSD-OTC"]
    assert (info["label"], info["category"], info["min"], info["max"], info["count"], info["payout"]) == (
        "EUR/USD (OTC)", "Moedas", 2, 20000, 5, 0.88)
    assert broker._instruments["BTCUSD-OTC"]["category"] == "Cripto"
    assert broker._instruments["XYZ-OTC"]["category"] == "Outros"
