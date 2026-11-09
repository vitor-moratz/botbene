"""Sinal que virou ordem: vale o resultado da corretora, não o das velas do bot.

A ordem pode entrar num preço diferente do toque (esperando o resultado do gale anterior, por exemplo).
Em 09/11 um CALL no AUDUSD-OTC deu loss pelas velas e a ordem ganhou: o acerto da estratégia tem de contar win.
"""

from app.broker.base import OrderResult
from app.db.database import Database
from app.paper import order_units
from app.service.events import EventHub
from app.service.orders import OrderManager
from app.service.resolver import PendingResolver
from tests.fakes import FakeBroker
from tests.helpers import random_walk
from tests.test_bot_service import approval_bot


def make_db(tmp_path):
    return Database(f"sqlite:///{tmp_path / 'b.sqlite'}")


def signal(db, entry_ts=1_000_020, direction="call", entry=0.685865):
    return db.add_signal(origin="ao_vivo", asset="AUDUSD-OTC", timeframe=60, strategy="bb_rci", direction=direction,
                         setup="Bollinger + RCI", candle_ts=entry_ts - 60, entry_ts=entry_ts, entry_price=entry,
                         payout=0.83, result="pendente", details={"touch": {"sec": 1.22}})


def order_for(db, sig, status, profit, amount=2.0):
    o = db.add_order(asset=sig["asset"], timeframe=60, strategy=sig["strategy"], direction=sig["direction"], amount=amount,
                     status="aberta", signal_id=sig["id"], requested_at=sig["entry_ts"] + 6)
    return db.update_order(o["id"], status=status, profit=profit)


def stored(db, sig_id):
    [row] = [s for s in db.list_signals(limit=50) if s["id"] == sig_id]
    return row


def test_ordem_fecha_depois_da_vela_e_troca_o_resultado(tmp_path):
    db = make_db(tmp_path)
    sig = signal(db)
    assert db.resolve_signal(sig["id"], entry=0.685865, exit_=0.685855, result="loss", profit=-1.0)["result"] == "loss"
    o = order_for(db, sig, "win", 1.66)
    row = db.apply_order_result(sig["id"], o["id"], "win", order_units("win", 1.66, 2.0))
    assert row["result"] == "win" and row["profit"] == 0.83
    assert row["exit_price"] == 0.685855  # os preços das velas ficam
    assert row["details"]["corretora"] == {"ordem": o["id"], "resultado": "win", "lucro": 0.83, "velas": "loss"}
    assert row["details"]["touch"] == {"sec": 1.22}  # o resto dos detalhes não se perde
    assert stored(db, sig["id"])["result"] == "win"


def test_ordem_fecha_antes_da_vela_e_a_vela_nao_desfaz(tmp_path):
    db = make_db(tmp_path)
    sig = signal(db)
    o = order_for(db, sig, "win", 1.66)
    row = db.apply_order_result(sig["id"], o["id"], "win", 0.83)
    assert row["result"] == "pendente"  # continua na fila das velas, para gravar a saída
    assert db.pending_signals("AUDUSD-OTC", 60)
    row = db.resolve_signal(sig["id"], entry=0.685865, exit_=0.685855, result="loss", profit=-1.0)
    assert row["result"] == "win" and row["profit"] == 0.83 and row["exit_price"] == 0.685855
    assert row["details"]["corretora"]["velas"] == "loss"
    assert not db.pending_signals("AUDUSD-OTC", 60)


def test_concordam_marca_a_corretora_sem_aviso(tmp_path):
    db = make_db(tmp_path)
    sig = signal(db)
    db.resolve_signal(sig["id"], entry=1.0, exit_=1.1, result="win", profit=0.83)
    o = order_for(db, sig, "win", 1.7)
    row = db.apply_order_result(sig["id"], o["id"], "win", order_units("win", 1.7, 2.0))
    assert row["result"] == "win" and row["profit"] == 0.85  # o payout pago de fato
    assert row["details"]["corretora"]["velas"] == "win"


def test_perda_e_empate_em_entradas(tmp_path):
    db = make_db(tmp_path)
    a, b = signal(db, 1_000_020), signal(db, 1_000_080)
    for s in (a, b):
        db.resolve_signal(s["id"], entry=1.0, exit_=1.1, result="win", profit=0.83)
    assert db.apply_order_result(a["id"], 1, "loss", order_units("loss", -2.0, 2.0))["profit"] == -1.0
    assert db.apply_order_result(b["id"], 2, "empate", order_units("empate", 0.0, 2.0))["profit"] == 0.0
    assert stored(db, a["id"])["result"] == "loss" and stored(db, b["id"])["result"] == "empate"


def test_vitoria_sem_valor_usa_o_payout_do_sinal(tmp_path):
    db = make_db(tmp_path)
    sig = signal(db)
    db.resolve_signal(sig["id"], entry=1.0, exit_=0.9, result="loss", profit=-1.0)
    assert order_units("win", None, 2.0) is None
    assert db.apply_order_result(sig["id"], 1, "win", None)["profit"] == 0.83


def test_ao_abrir_acerta_os_sinais_antigos_uma_vez_so(tmp_path):
    db = make_db(tmp_path)
    old, same, blocked, manual = signal(db, 1_000_020), signal(db, 1_000_080), signal(db, 1_000_140), signal(db, 1_000_200)
    db.resolve_signal(old["id"], entry=1.0, exit_=0.99, result="loss", profit=-1.0)
    db.resolve_signal(same["id"], entry=1.0, exit_=1.01, result="win", profit=0.83)
    db.resolve_signal(blocked["id"], entry=1.0, exit_=1.01, result="win", profit=0.83)
    db.resolve_signal(manual["id"], entry=1.0, exit_=1.01, result="win", profit=0.83)
    order_for(db, old, "win", 1.66)
    order_for(db, same, "win", 1.66)
    order_for(db, blocked, "bloqueada", None)
    order_for(db, manual, "sem_resultado", None)
    assert db.sync_order_results() == 2
    assert stored(db, old["id"])["result"] == "win"
    assert stored(db, old["id"])["details"]["corretora"]["velas"] == "loss"
    assert "corretora" not in stored(db, blocked["id"])["details"]  # sem resultado na corretora: fica o das velas
    assert "corretora" not in stored(db, manual["id"])["details"]
    assert db.sync_order_results() == 0
    assert stored(db, old["id"])["details"]["corretora"]["velas"] == "loss"  # não vira "win" na segunda vez


def test_cancelado_pelo_resolvedor_fica_com_o_da_corretora(tmp_path):
    db = make_db(tmp_path)
    candles = random_walk(50, seed=3)
    sig = signal(db, entry_ts=candles[-1].ts + 60 * 500)  # vela que a corretora não tem
    db.apply_order_result(sig["id"], 9, "loss", -1.0)
    PendingResolver(db, lambda: FakeBroker(candles, []), cancel_after=60).run_once(now=sig["entry_ts"] + 60 * 600)
    row = stored(db, sig["id"])
    assert row["result"] == "loss" and row["details"]["corretora"]["velas"] == "cancelado"


def test_gerenciador_de_ordens_passa_o_resultado_ao_sinal(tmp_path):
    db = make_db(tmp_path)
    hub = EventHub()
    events = []
    hub.publish = events.append
    candles = random_walk(10, seed=1)
    broker = FakeBroker(candles, [])
    om = OrderManager(db, hub, lambda: broker, sleep=lambda s: None, now=broker.server_time, threaded=False)
    sig = signal(db)
    db.resolve_signal(sig["id"], entry=0.685865, exit_=0.685855, result="loss", profit=-1.0)
    broker.results[1] = OrderResult("win", 1.66)
    om.submit(asset="AUDUSD-OTC", timeframe=60, strategy="bb_rci", direction="call", ref_price=0.685835,
              signal_id=sig["id"], payout=0.83)
    assert stored(db, sig["id"])["result"] == "win"
    [res] = [e for e in events if e["type"] == "result"]
    assert res["signal"]["id"] == sig["id"] and res["signal"]["result"] == "win"


def test_entrada_manual_nao_mexe_em_sinal(tmp_path):
    db = make_db(tmp_path)
    broker = FakeBroker(random_walk(10, seed=1), [])
    om = OrderManager(db, EventHub(), lambda: broker, sleep=lambda s: None, now=broker.server_time, threaded=False)
    om.submit_manual(asset="EURUSD", timeframe=60, direction="call", amount=2, minutes=1, ref_price=1.0,
                     requested_at=1, account=None)
    assert db.list_orders()[0]["status"] == "win" and db.list_signals(limit=5) == []


def test_bot_ao_vivo_sinal_segue_a_ordem(tmp_path):
    """A ordem do teste fecha na hora (antes da vela): quando a vela fecha, o sinal fica com o da corretora."""
    bot, broker, db, ap, nxt = approval_bot(tmp_path, mode="automatico")
    broker.results[1] = OrderResult("loss", -5.0)
    bot._poll(broker)  # tocou: ordem enviada e já fechada (loss)
    [order] = db.list_orders()
    assert order["status"] == "loss"
    for _ in range(3):
        bot._poll(broker)
    sig = stored(db, order["signal_id"])
    assert sig["result"] == "loss" and sig["profit"] == -1.0 and sig["exit_price"] is not None
    assert sig["details"]["corretora"]["velas"] in ("win", "loss", "empate")
