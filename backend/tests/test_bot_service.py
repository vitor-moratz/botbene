"""O bot de ponta a ponta, com corretora falsa: backtest no histórico, sinais ao vivo, vários pares,
avaliação paper e o modo de aprovação com ordem na demo."""

from app.config import Settings
from app.db.database import Database
from app.paper import judge
from app.risk import RiskConfig
from app.service.bot import BotService
from app.service.events import EventHub
from app.service.orders import OrderManager
from app.strategies import REGISTRY
from app.strategies.base import Direction
from app.strategies.ldp_apostila import ArmedSetup
from tests.fakes import FakeBroker
from tests.helpers import random_walk


def make_bot(tmp_path, n_live=60, assets=("EURUSD",), comparison=True):
    candles = random_walk(500 + n_live, seed=21)
    history, live = candles[:500], candles[500:]
    settings = Settings(_env_file=None, data_dir=tmp_path, history_candles=500)
    db = Database(settings.db_url())
    broker = FakeBroker(history, live)
    hub = EventHub()
    orders = OrderManager(db, hub, lambda: broker, sleep=lambda s: None, now=broker.server_time, threaded=False)
    bot = BotService(settings, db, hub, lambda: broker, orders=orders)
    bot.config.update({"comparison": comparison})
    bot.configure(list(assets), 60)
    return bot, broker, db, {c.ts: c for c in candles}


def test_sem_scripts_de_comparacao_so_a_principal_registra(tmp_path):
    bot, broker, db, _ = make_bot(tmp_path, comparison=False)
    bot._bootstrap(broker)
    for _ in range(60):
        bot._poll(broker)
    assert {s["strategy"] for s in db.list_signals(limit=5000)} <= {"retracao_comando"}
    assert bot.snapshot()["active_strategies"] == ["retracao_comando"]
    assert bot.runner().strategies == [] and [s.name for s in bot.runner().intra] == ["retracao_comando"]


def test_backtest_no_historico_avalia_com_a_vela_seguinte(tmp_path):
    bot, broker, db, by_ts = make_bot(tmp_path)
    bot._bootstrap(broker)
    rows = db.list_signals(origin="backtest", limit=5000)
    assert rows, "o backtest deveria gerar sinais"
    resolved = [r for r in rows if r["result"] in ("win", "loss", "empate")]
    assert resolved
    for r in resolved:
        entry = by_ts[r["entry_ts"]]
        assert r["entry_price"] == entry.open and r["exit_price"] == entry.close
        assert r["result"] == judge(r["direction"], entry.open, entry.close)
        assert r["payout"] == 0.8


def test_ao_vivo_registra_e_resolve_os_sinais(tmp_path):
    bot, broker, db, by_ts = make_bot(tmp_path)
    bot._bootstrap(broker)
    for _ in range(60):
        bot._poll(broker)
    live = db.list_signals(origin="ao_vivo", limit=5000)
    assert live, "esperava sinais ao vivo em 60 velas"
    last_closed = bot.runner().store.closed[-1].ts
    for r in live:
        assert r["entry_ts"] == r["candle_ts"] + 60
        if r["entry_ts"] <= last_closed:
            entry = by_ts[r["entry_ts"]]
            if r["strategy"] in REGISTRY:  # scripts de fechamento: entram na abertura da vela seguinte
                assert r["entry_price"] == entry.open
            assert r["exit_price"] == entry.close
            assert r["result"] == judge(r["direction"], r["entry_price"], entry.close)
        else:
            assert r["result"] == "pendente"  # a vela de entrada ainda está em formação


def test_sinal_ao_vivo_e_o_mesmo_do_backtest(tmp_path):
    """Sem repintura: rodar ao vivo dá os mesmos sinais que rodar o histórico inteiro depois."""
    bot, broker, db, _ = make_bot(tmp_path)
    bot._bootstrap(broker)
    for _ in range(60):
        bot._poll(broker)
    r = bot.runner()
    candles = r.store.closed
    live = {(x["strategy"], x["candle_ts"], x["direction"]) for x in db.list_signals(origin="ao_vivo", limit=5000)
            if x["strategy"] in REGISTRY}
    first_live_ts = candles[500].ts
    batch = set()
    for strat in r.strategies:
        for sig in strat.scan(candles):
            if sig is not None and sig.ts >= first_live_ts:
                batch.add((sig.strategy, sig.ts, sig.direction.value))
    assert live == batch


def test_varios_pares_ao_mesmo_tempo(tmp_path):
    bot, broker, db, _ = make_bot(tmp_path, n_live=5, assets=("EURUSD", "GBPUSD"))
    bot._bootstrap(broker)
    assert all(r.ready for r in bot.runners.values())
    assert {s["asset"] for s in db.list_signals(origin="backtest", limit=5000)} == {"EURUSD", "GBPUSD"}
    snap = bot.snapshot()
    assert [a["asset"] for a in snap["assets"]] == ["EURUSD", "GBPUSD"] and snap["asset"] == "EURUSD"
    bot.set_focus("GBPUSD")
    assert bot.snapshot()["asset"] == "GBPUSD" and bot.chart(100)["asset"] == "GBPUSD"


def armed_for(bot, candle, level, strategy="ldp_apostila"):
    r = bot.runner()
    prev = r.store.closed[-1]
    return ArmedSetup(direction=Direction.CALL, trigger="retracao", level_price=level, level_strength=3,
                      level_sources=["comando_unico:50%"], decision_index=len(r.store.closed) - 1, decision_ts=prev.ts,
                      target_ts=candle.ts, window_seconds=15, touch_tol=0.0, prev_close=prev.close, prev_range=prev.range,
                      gap_tol_pct=10.0, confluences={"gatilho": True}, strategy=strategy)


def test_gatilho_de_dentro_da_vela_entra_e_resolve(tmp_path):
    bot, broker, db, _ = make_bot(tmp_path, n_live=3)
    bot._bootstrap(broker)
    nxt = broker.live[0]
    bot.runner().armed = [armed_for(bot, nxt, nxt.low)]  # a vela vai tocar a marcação
    bot._poll(broker)  # vela entra em formação; 1 s depois da abertura: dentro da janela
    rows = db.list_signals(origin="ao_vivo", strategy="ldp_apostila")
    assert len(rows) == 1 and rows[0]["result"] == "pendente"
    assert rows[0]["entry_ts"] == nxt.ts and rows[0]["entry_price"] == nxt.close
    assert bot.armed_log[0]["outcome"] == "ENTROU"
    bot._poll(broker)  # a vela de entrada fecha: resultado com o preço de entrada gravado
    row = db.list_signals(origin="ao_vivo", strategy="ldp_apostila")[0]
    assert row["exit_price"] == nxt.close and row["result"] == judge("call", nxt.close, nxt.close)


def test_gatilho_que_nao_toca_nao_entra(tmp_path):
    bot, broker, db, _ = make_bot(tmp_path, n_live=3)
    bot._bootstrap(broker)
    nxt = broker.live[0]
    bot.runner().armed = [armed_for(bot, nxt, nxt.low - 1.0)]  # marcação longe: não toca
    bot._poll(broker)
    bot._poll(broker)
    assert not db.list_signals(origin="ao_vivo", strategy="ldp_apostila")
    assert bot.armed_log[0]["outcome"] == "não acionado"


# ---------------------------------------------------------------------- modo de aprovação


def approval_bot(tmp_path, level_offset=0.0, risk=None, mode="aprovacao"):
    bot, broker, db, by_ts = make_bot(tmp_path, n_live=3)
    bot._bootstrap(broker)
    bot.mode, bot.order_strategies = mode, {"retracao_comando"}
    bot.orders.reset(risk or RiskConfig(stake=5, stop_win=None, stop_loss=None))
    nxt = broker.live[0]
    a = armed_for(bot, nxt, nxt.low - level_offset, strategy="retracao_comando")
    r = bot.runner()
    r.armed = [a]
    [ap] = bot._open_approvals(r, r.armed, now=nxt.ts - 1)
    assert ap["status"] == ("aguardando" if mode == "aprovacao" else "aprovado") and len(ap["excerpt"]) == 60
    return bot, broker, db, ap, nxt


def test_automatico_entra_sozinho(tmp_path):
    bot, broker, db, ap, nxt = approval_bot(tmp_path, mode="automatico")
    assert ap["auto"] and not ap["veto"]
    bot._poll(broker)  # tocou: ordem sem ninguém clicar
    assert ap["status"] == "ordem enviada" and len(broker.tickets) == 1
    assert ap["open_price"] == nxt.open


def test_automatico_com_veto_pode_cancelar(tmp_path):
    bot, broker, db, ap, _ = approval_bot(tmp_path, mode="automatico_veto")
    assert ap["auto"] and ap["veto"]
    assert bot.decide(ap["id"], False)["status"] == "cancelado por você"
    bot._poll(broker)
    assert not broker.tickets and not db.list_orders()


def test_cancelar_depois_de_aprovar(tmp_path):
    bot, broker, db, ap, _ = approval_bot(tmp_path)
    bot.decide(ap["id"], True)
    assert bot.decide(ap["id"], False)["status"] == "cancelado por você"
    bot._poll(broker)
    assert not broker.tickets


def test_aprovado_antes_do_gatilho_manda_ordem_no_toque(tmp_path):
    bot, broker, db, ap, nxt = approval_bot(tmp_path)
    assert bot.decide(ap["id"], True)["status"] == "aprovado"
    assert not broker.tickets
    bot._poll(broker)  # tocou: ordem enviada
    assert ap["status"] == "ordem enviada"
    [t] = broker.tickets
    assert (t.asset, t.direction, t.amount) == ("EURUSD", "call", 5)
    [order] = db.list_orders()
    assert order["status"] == "win" and order["profit"] == 4.0 and order["signal_id"] is not None
    assert bot.orders.snapshot()["pnl"] == 4.0


def test_aprovado_depois_do_toque_entra_no_preco_do_momento(tmp_path):
    bot, broker, db, ap, nxt = approval_bot(tmp_path)
    bot._poll(broker)  # tocou sem aprovação
    assert ap["status"] == "disparou" and not broker.tickets
    assert bot.decide(ap["id"], True)["status"] == "ordem enviada"
    assert len(broker.tickets) == 1 and db.list_orders()[0]["ref_price"] == nxt.close


def test_rejeitado_nao_manda_ordem(tmp_path):
    bot, broker, db, ap, _ = approval_bot(tmp_path)
    bot.decide(ap["id"], False)
    bot._poll(broker)
    assert ap["status"] == "rejeitado" and not broker.tickets and not db.list_orders()
    assert db.list_signals(origin="ao_vivo", strategy="retracao_comando")  # o sinal paper continua registrado


def test_sem_resposta_expira(tmp_path):
    bot, broker, db, ap, _ = approval_bot(tmp_path)
    bot._poll(broker)  # disparou
    bot._poll(broker)  # próxima vela: passou da janela
    assert ap["status"] == "expirou sem resposta" and not broker.tickets


def test_aprovado_que_nao_dispara(tmp_path):
    bot, broker, db, ap, _ = approval_bot(tmp_path, level_offset=1.0)
    bot.decide(ap["id"], True)
    bot._poll(broker)
    bot._poll(broker)
    assert ap["status"] == "não disparou" and not broker.tickets


def test_gestao_de_risco_bloqueia(tmp_path):
    bot, broker, db, ap, _ = approval_bot(tmp_path, risk=RiskConfig(stake=5, stop_win=None, stop_loss=3, max_trades=None))
    bot.decide(ap["id"], True)
    bot._poll(broker)
    assert ap["status"] == "bloqueada" and "stop loss" in ap["note"]
    assert not broker.tickets and db.list_orders()[0]["status"] == "bloqueada"


def test_corretora_recusa_vira_erro(tmp_path):
    bot, broker, db, ap, _ = approval_bot(tmp_path)
    broker.refuse_orders = "saldo insuficiente"
    bot.decide(ap["id"], True)
    bot._poll(broker)
    order = db.list_orders()[0]
    assert order["status"] == "erro" and "saldo" in order["error"]
    assert bot.orders.snapshot()["open_orders"] == 0


def test_modo_so_sinais_nao_pede_aprovacao(tmp_path):
    bot, broker, db, _ = make_bot(tmp_path, n_live=3)
    bot._bootstrap(broker)
    r = bot.runner()
    nxt = broker.live[0]
    assert bot.mode == "sinais"
    assert bot._open_approvals(r, [armed_for(bot, nxt, nxt.low, strategy="retracao_comando")], now=nxt.ts - 1) == []


def test_snapshot_e_grafico(tmp_path):
    bot, broker, db, _ = make_bot(tmp_path)
    bot._bootstrap(broker)
    bot._poll(broker)
    snap = bot.snapshot()
    assert snap["asset"] == "EURUSD" and snap["payout"] == 0.8 and snap["mode"] == "sinais"
    assert snap["reading"]["classe"] and snap["risk"]["can_trade"]
    chart = bot.chart(300)
    assert len(chart["candles"]) == 300
    assert len(chart["buy_line"]) == 300
    assert all(m["time"] >= chart["candles"][0]["time"] for m in chart["markers"])
