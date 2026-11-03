"""Ordens: vencimento da binária de 1 min, ativo aberto e leitura do resultado vindo da IQ."""

import time
from types import SimpleNamespace

import pytest

from app.broker.base import AccountType, BrokerError, OrderTicket, expiry_for
from app.broker.iqoption import IQOptionBroker


def test_vencimento_no_fim_do_minuto_atual_ate_os_30s():
    base = 1_700_000_040  # múltiplo de 60
    assert expiry_for(base + 0) == base + 60
    assert expiry_for(base + 15) == base + 60
    assert expiry_for(base + 29) == base + 60
    assert expiry_for(base + 30) == base + 120  # com 30 s ou menos a IQ joga para o minuto seguinte
    assert expiry_for(base + 45) == base + 120


class FakeApi:
    def __init__(self, closed=None, binary=None, buy_answer=(True, 123)):
        self.api = SimpleNamespace(socket_option_closed=closed or {}, order_binary=binary or {})
        self.buy_answer = buy_answer
        self.bought = []

    def get_server_timestamp(self):
        return time.time() - 29  # relógio local adiantado, como no WSL: não pode afetar o vencimento

    def buy_by_raw_expirations(self, amount, asset, direction, option, expired):
        self.bought.append((amount, asset, direction, option, expired))
        return self.buy_answer


OPEN = {"id": 1861, "kind": "turbo", "enabled": True, "suspended": False, "schedule": [[0, 4_000_000_000]], "payout": 0.84}


def broker_with(api, account=AccountType.PRACTICE, allow_real=False, instruments=None):
    b = IQOptionBroker("a@b.c", "x", allow_real=allow_real, request_pause=0)
    b._api = api
    b._account = account
    b._instruments = {"EURUSD-op": dict(OPEN)} if instruments is None else instruments
    b._instruments_at = time.time()
    return b


def test_envia_ordem_na_demo_com_vencimento_pelo_horario_da_iq():
    api = FakeApi()
    b = broker_with(api)
    t = b.buy("EURUSD-op", "call", 2.0)
    [(amount, asset, direction, option, expired)] = api.bought
    assert (amount, asset, direction, option) == (2.0, "EURUSD-op", "call", "turbo")
    assert expired == t.expires_at == expiry_for(t.opened_at)
    assert t.order_id == 123 and t.account == "PRACTICE"


def test_real_bloqueada_nao_envia():
    api = FakeApi()
    with pytest.raises(BrokerError, match="REAL bloqueada"):
        broker_with(api, AccountType.REAL).buy("EURUSD-op", "call", 2.0)
    assert api.bought == []


def test_ativo_fechado_ou_fora_da_lista_nao_envia():
    api = FakeApi()
    closed = dict(OPEN, suspended=True)
    with pytest.raises(BrokerError, match="fechado"):
        broker_with(api, instruments={"EURUSD-op": closed}).buy("EURUSD-op", "call", 2.0)
    with pytest.raises(BrokerError, match="-op"):
        broker_with(api).buy("EURUSD", "call", 2.0)
    assert api.bought == []


def test_ordem_recusada_vira_erro():
    with pytest.raises(BrokerError, match="recusou"):
        broker_with(FakeApi(buy_answer=(False, "saldo insuficiente"))).buy("EURUSD-op", "put", 2.0)


@pytest.mark.parametrize("win,amount_back,expected", [("win", 3.7, ("win", 1.7)), ("loose", 0, ("loss", -2.0)), ("equal", 2.0, ("empate", 0.0))])
def test_resultado_pelo_aviso_da_iq(win, amount_back, expected):
    closed = {123: {"msg": {"win": win, "win_amount": amount_back, "sum": 2.0}}}
    b = broker_with(FakeApi(closed=closed))
    r = b.order_result(OrderTicket(123, "EURUSD-op", "call", 2.0, "PRACTICE", 0, 60))
    assert (r.result, r.profit) == expected


def test_resultado_pelo_aviso_option_closed():
    binary = {123: {"option_id": 123, "result": "win", "profit_amount": 3.68, "amount": 2.0}}
    r = broker_with(FakeApi(binary=binary)).order_result(OrderTicket(123, "EURUSD-op", "call", 2.0, "PRACTICE", 0, 60))
    assert (r.result, r.profit) == ("win", 1.68)


def test_resultado_ainda_aberto_nao_espera():
    b = broker_with(FakeApi())
    start = time.time()
    assert b.order_result(OrderTicket(123, "EURUSD-op", "call", 2.0, "PRACTICE", time.time(), int(time.time()) - 100)) is None
    assert time.time() - start < 0.5  # nunca trava esperando a IQ
