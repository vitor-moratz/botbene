import time

import pytest

from app.broker.base import BrokerError
from app.broker.iqoption import call_with_deadline


def test_retorna_o_resultado_quando_responde_a_tempo():
    assert call_with_deadline("rápida", lambda: 42, timeout=1) == 42


def test_erro_claro_quando_a_iq_nao_responde():
    with pytest.raises(BrokerError, match="não respondeu a 'lenta'"):
        call_with_deadline("lenta", lambda: time.sleep(2), timeout=0.1)


def test_repassa_o_erro_original():
    def boom():
        raise ValueError("falhou")

    with pytest.raises(ValueError, match="falhou"):
        call_with_deadline("com erro", boom, timeout=1)
