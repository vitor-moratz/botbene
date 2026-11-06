"""Desenho do script LDP v1.3 no gráfico: linhas e setas saem das velas, sem gravar sinal nem mandar ordem."""

import json

from app.service.chart import build_reading, ldp_overlay, order_entries
from app.strategies.ldp_v13 import LdpV13
from tests.helpers import random_walk
from tests.test_bot_service import approval_bot, make_bot


def test_setas_e_linhas_iguais_ao_script():
    candles = random_walk(400, seed=3)
    res = LdpV13().analyze(candles)
    overlay = ldp_overlay(candles, start=100)
    expected = [(s.ts, s.direction.value, s.setup) for s in res.signals[100:] if s is not None]
    assert expected, "o trecho deveria ter sinais"
    assert [(m["time"], m["direction"], m["setup"]) for m in overlay["script_marks"]] == expected
    assert len(overlay["buy_line"]) == len(overlay["sell_line"]) == 300
    for k, point in zip(range(100, 400), overlay["buy_line"]):
        assert point["time"] == candles[k].ts and point.get("value") == res.buy_line[k]


def test_vela_em_formacao_ja_mostra_a_linha_que_vale_agora():
    candles = random_walk(400, seed=3)
    res = LdpV13().analyze(candles)
    k = next(i for i in range(50, 400) if res.cmd_up[i])  # o comando fecha: a linha muda na vela seguinte
    closed = candles[: k + 1]
    next_ts = closed[-1].ts + 60
    last = ldp_overlay(closed, next_ts=next_ts)["buy_line"][-1]
    assert last == {"time": next_ts, "value": closed[-1].mid}


def test_vela_ja_fechada_nao_ganha_ponto_extra():
    candles = random_walk(100, seed=3)
    assert len(ldp_overlay(candles, next_ts=candles[-1].ts)["buy_line"]) == 100
    assert ldp_overlay([], next_ts=60) == {"buy_line": [], "sell_line": [], "script_marks": []}


def test_setas_do_script_nao_viram_sinal_nem_ordem(tmp_path):
    bot, broker, db, _ = make_bot(tmp_path, closing=False)
    bot._bootstrap(broker)
    for _ in range(20):
        bot._poll(broker)
    chart = bot.chart(300)
    assert chart["script_marks"]
    assert {s["strategy"] for s in db.list_signals(limit=5000)} <= {"retracao_comando"}
    assert not [m for m in chart["markers"] if m["strategy"] == "ldp_v13"]
    assert not broker.tickets


def test_wiki_pro_so_quando_ligado(tmp_path):
    bot, broker, db, _ = make_bot(tmp_path, closing=False)
    bot._bootstrap(broker)
    assert bot.chart(300)["wiki_marks"] == []
    bot.config.update({"chart_scripts": {"wiki_pro": True}})
    marks = bot.chart(300)["wiki_marks"]
    assert marks and all(m["direction"] in ("call", "put") for m in marks)
    assert {s["strategy"] for s in db.list_signals(limit=5000)} <= {"retracao_comando"}  # continua só desenho


def order(**over):
    return {"id": 1, "signal_id": None, "direction": "call", "status": "aberta", "ref_price": 1.5, "amount": 2.0,
            "profit": None, "account": "PRACTICE", "strategy": "retracao_comando", "expires_at": 660, "requested_at": 605} | over


def test_entrada_cai_na_vela_do_sinal_com_o_preco_da_ordem():
    signal = {"id": 7, "entry_ts": 600, "entry_price": 1.4, "setup": "retração no comando"}
    [e] = order_entries([order(signal_id=7, status="win", profit=1.68)], [signal], 60, 0)
    assert (e["time"], e["price"], e["status"], e["profit"], e["setup"]) == (600, 1.5, "win", 1.68, "retração no comando")


def test_entrada_sem_o_sinal_usa_o_vencimento_ou_o_horario_do_pedido():
    assert order_entries([order()], [], 60, 0)[0]["time"] == 600  # vence às 660: entrou na vela das 600
    assert order_entries([order(expires_at=None)], [], 60, 0)[0]["time"] == 600
    signal = {"id": 7, "entry_ts": 600, "entry_price": 1.4, "setup": "x"}
    assert order_entries([order(ref_price=None, signal_id=7)], [signal], 60, 0)[0]["price"] == 1.4  # sem preço na ordem: o do sinal


def test_ordem_que_nao_chegou_a_corretora_nao_e_entrada():
    assert order_entries([order(status="bloqueada"), order(status="erro")], [], 60, 0) == []


def test_entrada_antes_do_trecho_do_grafico_fica_de_fora():
    assert order_entries([order()], [], 60, 601) == []


def test_ordem_real_aparece_no_grafico_e_o_sinal_dela_e_identificado(tmp_path):
    bot, broker, _, ap, nxt = approval_bot(tmp_path, mode="automatico")
    bot._poll(broker)  # tocou o gatilho: ordem enviada
    assert ap["status"] == "ordem enviada"
    chart = bot.chart(300)
    [entry] = chart["entries"]
    assert entry["time"] == nxt.ts and entry["direction"] == ap["direction"] and entry["signal_id"] == ap["signal_id"]
    assert entry["price"] is not None and entry["strategy"] == "retracao_comando"
    assert ap["signal_id"] in {m["id"] for m in chart["markers"]}  # o painel troca a seta dele pela marca de ENTRADA


def test_grafico_so_traz_as_ordens_do_par(tmp_path):
    bot, broker, db, ap, _ = approval_bot(tmp_path, mode="automatico")
    bot._poll(broker)
    db.add_order(asset="GBPUSD", timeframe=60, strategy="retracao_comando", direction="put", amount=2.0, status="aberta")
    assert [e["direction"] for e in bot.chart(300)["entries"]] == [ap["direction"]]


def test_leitura_traz_lotes_regioes_e_rotulos_so_do_trecho_mostrado():
    candles = random_walk(500, seed=3)
    data = build_reading("EURUSD", 60, candles, 200)
    first = candles[300].ts
    assert data["lots"] and all(lot["to"] >= first for lot in data["lots"])
    assert data["regions"] and data["tags"] and all(t["time"] >= first for t in data["tags"])
    assert {t["code"] for t in data["tags"]} & {"NA", "NB"}
    assert all(r["low"] <= r["high"] and r["side"] in (-1, 0, 1) for r in data["regions"])
    assert any(r["active"] for r in data["regions"]) and data["scenario"] in ("topos_fundos", "tendencia", "consolidacao")
    assert data["scenarios"][0]["from"] == first and data["scenarios"][-1]["to"] == candles[-1].ts
    json.dumps(data)  # vai para o painel


def test_leitura_sem_velas():
    assert build_reading("", 60, [], 200)["lots"] == []


def test_leitura_nao_grava_sinal_nem_manda_ordem(tmp_path):
    bot, broker, db, _ = make_bot(tmp_path, closing=False)
    bot._bootstrap(broker)
    before = len(db.list_signals(limit=5000))
    assert bot.reading_view(200)["lots"]
    assert len(db.list_signals(limit=5000)) == before and not broker.tickets


def test_pedido_leva_linhas_e_setas_enquanto_esta_aberto(tmp_path):
    bot, _, _, ap, _ = approval_bot(tmp_path)
    overlay = ap["overlay"]
    first, last = ap["excerpt"][0]["time"], ap["excerpt"][-1]["time"]
    assert len(overlay["buy_line"]) == len(ap["excerpt"]) + 1
    assert overlay["buy_line"][-1]["time"] == ap["target_ts"] > last
    assert all(first <= m["time"] <= last for m in overlay["script_marks"])
    bot.decide(ap["id"], False)
    assert ap["excerpt"] is None and ap["overlay"] is None
