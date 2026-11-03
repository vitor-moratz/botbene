"""Sem repintura: o resultado de uma vela não pode mudar quando chegam velas novas.

Compara o processamento do histórico inteiro com o de cada prefixo (como seria ao vivo).
"""

import pytest

from app.ldp.engine import LdpEngine
from app.strategies.ldp_v13 import LdpV13
from app.strategies.wiki_pro_v21 import WikiProV21
from tests.helpers import random_walk

CANDLES = random_walk(400, seed=11)
CUTS = range(60, 400, 37)


@pytest.mark.parametrize("strategy", [LdpV13(), WikiProV21()], ids=lambda s: s.name)
def test_strategy_signals_do_not_change(strategy):
    full = strategy.scan(CANDLES)
    for cut in CUTS:
        assert strategy.scan(CANDLES[:cut]) == full[:cut], f"sinal mudou ao cortar em {cut}"


def test_engine_live_equals_batch():
    batch = LdpEngine().run(CANDLES)
    live_engine = LdpEngine()
    live = [live_engine.process(c) for c in CANDLES]
    for a, b in zip(batch, live):
        assert a.structures == b.structures
        assert a.info == b.info
    for cut in CUTS:
        prefix = LdpEngine().run(CANDLES[:cut])
        assert [s.structures for s in prefix] == [s.structures for s in batch[:cut]]
