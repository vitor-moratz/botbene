"""Filtros de entrada: payout mínimo e horário de operação (Brasília)."""

from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from app.analytics.timeline import BRT
from app.service.config_store import UserConfig
from tests.test_bot_service import approval_bot, armed_for, make_bot


def brt(hh, mm=0):
    return datetime(2026, 11, 3, hh, mm, tzinfo=BRT).timestamp()


def test_horario_valida_e_normaliza():
    cfg = UserConfig(hours_start="9:5", hours_end="17:00")
    assert (cfg.hours_start, cfg.hours_end) == ("09:05", "17:00")
    assert UserConfig(hours_start="", hours_end="  ").hours_start is None  # vazio = o dia todo
    for bad in ({"hours_start": "25:00", "hours_end": "26:00"}, {"hours_start": "09:00"},
                {"hours_start": "10:00", "hours_end": "10:00"}, {"hours_start": "9h", "hours_end": "10h"}):
        with pytest.raises(ValidationError):
            UserConfig(**bad)


def test_payout_minimo():
    cfg = UserConfig(min_payout=0.80)
    assert cfg.entry_block(0.80, brt(12)) is None
    assert cfg.entry_block(0.86, brt(12)) is None
    assert "payout de 78% abaixo do mínimo de 80%" in cfg.entry_block(0.78, brt(12))
    assert UserConfig(min_payout=None).entry_block(0.5, brt(12)) is None
    assert UserConfig().min_payout == 0.80  # padrão


def test_horario_de_operacao():
    cfg = UserConfig(hours_start="09:00", hours_end="17:00")
    assert cfg.entry_block(0.85, brt(9)) is None
    assert cfg.entry_block(0.85, brt(16, 59)) is None
    assert "fora do horário de operação (09:00–17:00)" in cfg.entry_block(0.85, brt(17))
    assert cfg.entry_block(0.85, brt(8, 59))
    night = UserConfig(hours_start="22:00", hours_end="02:00")  # passa da meia-noite
    assert night.entry_block(0.85, brt(23, 30)) is None
    assert night.entry_block(0.85, brt(1, 59)) is None
    assert night.entry_block(0.85, brt(3))


def test_payout_baixo_nao_abre_pedido_mas_continua_medindo(tmp_path):
    bot, broker, db, _ = make_bot(tmp_path, n_live=3)
    bot._bootstrap(broker)
    bot.mode, bot.order_strategies = "automatico", {"retracao_comando"}
    nxt = broker.live[0]
    r = bot.runner()
    r.payout = 0.75
    r.armed = [armed_for(bot, nxt, nxt.low, strategy="retracao_comando")]
    assert bot._open_approvals(r, r.armed, now=nxt.ts - 1) == []
    assert "payout de 75%" in bot.armed_log[0]["outcome"]
    bot._poll(broker)  # o preço toca o gatilho
    assert not broker.tickets and not db.list_orders()
    assert db.list_signals(origin="ao_vivo", strategy="retracao_comando")  # o sinal entra na estatística


def test_fora_do_horario_nao_abre_pedido(tmp_path):
    bot, broker, db, _ = make_bot(tmp_path, n_live=3)
    bot._bootstrap(broker)
    bot.mode, bot.order_strategies = "automatico", {"retracao_comando"}
    nxt = broker.live[0]
    when = datetime.fromtimestamp(nxt.ts, tz=BRT)
    start, end = (when + timedelta(hours=2)).strftime("%H:%M"), (when + timedelta(hours=3)).strftime("%H:%M")
    bot.filters = UserConfig(hours_start=start, hours_end=end)
    r = bot.runner()
    r.armed = [armed_for(bot, nxt, nxt.low, strategy="retracao_comando")]
    assert bot._open_approvals(r, r.armed, now=nxt.ts - 1) == []
    assert "fora do horário" in bot.armed_log[0]["outcome"]


def test_payout_que_cai_antes_do_gatilho_bloqueia_a_ordem(tmp_path):
    bot, broker, db, ap, _ = approval_bot(tmp_path, mode="automatico")
    bot.runner().payout = 0.70
    bot._poll(broker)  # tocou o gatilho, mas o payout caiu
    assert ap["status"] == "bloqueada" and "payout de 70%" in ap["note"]
    assert not broker.tickets
