"""Gravador do sentimento dos traders (plano de 09/11/2026, frente F1)."""

import time
from types import SimpleNamespace

import pytest

from app.broker.base import BrokerError
from app.broker.iqoption import MOOD_INSTRUMENT, IQOptionBroker
from app.config import Settings
from app.research.dataset import research_db
from app.service.config_store import ConfigStore
from app.service.mood import MAX_AGE, RESUBSCRIBE_AGE, MoodRecorder
from tests.fakes import FakeBroker


def recorder(tmp_path, broker, assets=("EURUSD-OTC", "GBPUSD-OTC")):
    db = research_db(Settings(_env_file=None, data_dir=tmp_path))
    config = ConfigStore(tmp_path / "config.json")
    config.update({"assets": list(assets)})
    return MoodRecorder(db, lambda: broker, config, extra_assets=(), flush_seconds=0), db


def test_grava_no_relogio_de_5s_so_os_pares_com_valor(tmp_path):
    broker = FakeBroker([], [])
    broker._last_ts = 1_000_002  # server_time = 1_000_003: a amostra cai na marca de 1_000_000
    broker.moods = {"EURUSD-OTC": (0.62, 1.5)}
    rec, db = recorder(tmp_path, broker)
    assert rec.run_once() == 1
    assert db.load_mood("EURUSD-OTC") == [(1_000_000, 0.62, 1.5)]
    assert db.load_mood("GBPUSD-OTC") == []
    rec.run_once()  # a mesma marca de novo não duplica
    assert len(db.load_mood("EURUSD-OTC")) == 1


def test_valor_parado_pede_de_novo_e_valor_velho_demais_nao_entra(tmp_path):
    broker = FakeBroker([], [])
    broker.moods = {"EURUSD-OTC": (0.4, RESUBSCRIBE_AGE + 1), "GBPUSD-OTC": (0.5, MAX_AGE + 1)}
    rec, db = recorder(tmp_path, broker)
    assert rec.run_once() == 1  # só o EURUSD (o GBPUSD está parado há mais de MAX_AGE)
    assert ("EURUSD-OTC", True) in broker.mood_calls
    calls = len(broker.mood_calls)
    rec.run_once()  # não pede de novo a cada 5 s
    assert ("EURUSD-OTC", True) not in broker.mood_calls[calls:]


def test_sem_conexao_do_bot_nao_faz_nada(tmp_path):
    rec, db = recorder(tmp_path, None)
    assert rec.run_once() == 0
    broker = FakeBroker([], [])
    broker.is_connected = lambda: False
    broker.moods = {"EURUSD-OTC": (0.6, 1.0)}
    rec2, _ = recorder(tmp_path / "b", broker)
    assert rec2.run_once() == 0 and broker.mood_calls == []


def test_um_par_com_erro_nao_para_os_outros(tmp_path):
    broker = FakeBroker([], [])
    broker.moods = {"EURUSD-OTC": (0.6, 1.0), "GBPUSD-OTC": (0.3, 1.0)}

    def subscribe(asset, force=False):
        if asset == "EURUSD-OTC":
            raise BrokerError("sem resposta")
        return True

    broker.subscribe_mood = subscribe
    rec, db = recorder(tmp_path, broker)
    assert rec.run_once() == 1
    assert db.load_mood("GBPUSD-OTC")[0][1] == 0.3


def test_mesmos_pares_do_arquivo_de_velas(tmp_path):
    config = ConfigStore(tmp_path / "config.json")
    config.update({"assets": ["EURUSD-OTC", "EURUSD-op"]})
    rec = MoodRecorder(research_db(Settings(_env_file=None, data_dir=tmp_path)), lambda: None, config)
    assert rec.assets()[:2] == ["EURUSD-OTC", "EURUSD-op"] and "AUDJPY-op" in rec.assets()


def test_thread_grava_e_para(tmp_path):
    broker = FakeBroker([], [])
    broker.moods = {"EURUSD-OTC": (0.55, 0.5)}
    db = research_db(Settings(_env_file=None, data_dir=tmp_path))
    config = ConfigStore(tmp_path / "config.json")
    config.update({"assets": ["EURUSD-OTC"]})
    rec = MoodRecorder(db, lambda: broker, config, extra_assets=(), step=1, flush_seconds=1000, first_delay=0)
    rec.start()
    time.sleep(0.3)
    rec.stop()  # o que estava no lote é gravado ao parar
    assert db.load_mood("EURUSD-OTC")


# ---------------------------------------------------------------------- adaptador da IQ


def iq_with_fake_api():
    pytest.importorskip("iqoptionapi")
    asked = []
    inner = SimpleNamespace(subscribe_Traders_mood=lambda active, instrument: asked.append((active, instrument)))
    b = IQOptionBroker("a@b.c", "x")
    b._api = SimpleNamespace(api=inner)
    return b, inner, asked


def test_iq_assina_uma_vez_por_conexao_e_le_com_idade():
    from iqoptionapi import constants as op_code
    from iqoptionapi.ws.received.traders_mood_changed import traders_mood_changed

    b, inner, asked = iq_with_fake_api()
    aid = op_code.ACTIVES["EURUSD"]
    assert b.traders_mood("EURUSD") is None
    assert b.subscribe_mood("EURUSD") and b.subscribe_mood("EURUSD")
    assert asked == [(aid, MOOD_INSTRUMENT)]
    # o aviso da IQ, tratado pela própria biblioteca, cai no dicionário desta conexão
    traders_mood_changed(inner, {"name": "traders-mood-changed", "msg": {"asset_id": aid, "value": 0.71}})
    value, age = b.traders_mood("EURUSD")
    assert value == 0.71 and 0 <= age < 1
    assert b.subscribe_mood("EURUSD", force=True) and len(asked) == 2


def test_iq_conexao_nova_esquece_valor_e_assinatura_da_antiga():
    from iqoptionapi import constants as op_code

    b, inner, asked = iq_with_fake_api()
    aid = op_code.ACTIVES["EURUSD"]
    b.subscribe_mood("EURUSD")
    inner.traders_mood[aid] = 0.3
    b._api = SimpleNamespace(api=SimpleNamespace(subscribe_Traders_mood=lambda a, i: asked.append((a, i))))
    assert b.traders_mood("EURUSD") is None  # nada da conexão antiga
    b.subscribe_mood("EURUSD")
    assert len(asked) == 2  # assinou de novo na conexão nova


def test_iq_par_desconhecido_ou_sem_conexao():
    b, _, asked = iq_with_fake_api()
    assert not b.subscribe_mood("NAOEXISTE-op") and b.traders_mood("NAOEXISTE-op") is None and asked == []
    b._api = None
    assert not b.subscribe_mood("EURUSD") and b.traders_mood("EURUSD") is None
