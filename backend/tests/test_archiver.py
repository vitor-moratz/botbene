"""Arquivo automático de velas para a pesquisa: só busca o que ainda não tem."""

from app.config import Settings
from app.research.dataset import load, research_db
from app.service.archiver import ResearchArchiver
from app.service.config_store import ConfigStore
from tests.fakes import FakeBroker
from tests.helpers import random_walk


def test_guarda_e_depois_so_busca_o_que_falta(tmp_path):
    candles = random_walk(1200, seed=6)
    broker = FakeBroker(candles, [], archive=candles)
    broker._last_ts = candles[-1].ts + 60  # horário do servidor: depois da última vela
    db = research_db(Settings(_env_file=None, data_dir=tmp_path))
    config = ConfigStore(tmp_path / "config.json")
    config.update({"assets": ["EURUSD-op"]})
    arch = ResearchArchiver(db, lambda: broker, config, extra_assets=())
    assert arch.run_once() == 1200
    assert len(load(db, "EURUSD-op", 60)) == 1200
    calls = broker.get_candles_calls
    assert arch.run_once() <= 2  # só a emenda (últimas velas de novo)
    assert broker.get_candles_calls - calls <= 4


def test_guarda_os_pares_da_pesquisa_mesmo_fora_da_configuracao(tmp_path):
    config = ConfigStore(tmp_path / "config.json")
    config.update({"assets": ["EURUSD-OTC", "EURUSD-op"]})
    arch = ResearchArchiver(research_db(Settings(_env_file=None, data_dir=tmp_path)), lambda: None, config)
    assets = arch.assets()
    assert assets[:2] == ["EURUSD-OTC", "EURUSD-op"] and len(assets) == 13  # sem repetir o EURUSD-op
    assert {"AUDJPY-op", "NZDUSD-op", "GBPJPY-op", "AUDCAD-op", "EURNZD-op", "GBPAUD-op"} <= set(assets)
