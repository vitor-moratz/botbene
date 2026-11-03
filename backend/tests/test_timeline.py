from datetime import datetime

from app.analytics.timeline import BRT, cumulative, period_start, timeline

NOW = datetime(2026, 11, 2, 22, 30, tzinfo=BRT)


def ts(day, hour=12, minute=0, month=11):
    return int(datetime(2026, month, day, hour, minute, tzinfo=BRT).timestamp())


def row(entry_ts, result, profit):
    return {"entry_ts": entry_ts, "result": result, "profit": profit}


def test_inicio_dos_periodos_no_horario_de_brasilia():
    assert period_start("hoje", NOW) == ts(2, 0)
    assert period_start("7d", NOW) == ts(27, 0, month=10)
    assert period_start("mes", NOW) == ts(1, 0)
    assert period_start("geral", NOW) is None


def test_hoje_agrupa_por_hora_sem_buracos():
    rows = [row(ts(2, 9, 5), "win", 0.85), row(ts(2, 9, 40), "loss", -1.0), row(ts(2, 21, 0), "win", 0.85)]
    tl = timeline(rows, "hoje", NOW)
    assert [b["label"] for b in tl][:3] == ["00h", "01h", "02h"]
    assert len(tl) == 23  # 00h até 22h
    nine = tl[9]
    assert (nine["wins"], nine["losses"], nine["profit"]) == (1, 1, -0.15)
    assert tl[21]["winrate"] == 1.0 and tl[10]["n"] == 0


def test_mes_agrupa_por_dia():
    tl = timeline([row(ts(1, 10), "win", 0.85)], "mes", NOW)
    assert [b["label"] for b in tl] == ["01/11", "02/11"]


def test_geral_agrupa_por_mes():
    rows = [row(ts(15, month=9), "win", 0.85), row(ts(2), "loss", -1.0)]
    assert [b["label"] for b in timeline(rows, "geral", NOW)] == ["09/2026", "10/2026", "11/2026"]


def test_saldo_acumulado_soma_scripts_na_mesma_vela():
    rows = [row(100, "win", 0.85), row(100, "loss", -1.0), row(160, "win", 0.85)]
    assert cumulative(rows) == [{"time": 100, "value": -0.15}, {"time": 160, "value": 0.7}]
