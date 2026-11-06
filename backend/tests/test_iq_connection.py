"""Conexão com a IQ: threads presas encerradas no prazo, conexão morta percebida, login sem sessão velha."""

import threading
import time
from types import SimpleNamespace

import pytest

from app.broker.base import BrokerError
from app.broker.iqoption import CLOCK_FROZEN_SECONDS, MAX_STUCK_CALLS, IQOptionBroker, call_with_deadline, stuck_calls


def wait_gone(names, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not [t for t in threading.enumerate() if t.name in names]:
            return True
        time.sleep(0.05)
    return False


def test_thread_em_laco_sem_pausa_e_encerrada_no_prazo():
    """É assim que a biblioteca espera: sem encerrar, cada chamada sem resposta gasta CPU para sempre."""
    never = []

    def spin():
        while not never:
            pass

    with pytest.raises(BrokerError):
        call_with_deadline("laço", spin, timeout=0.05)
    assert wait_gone({"iq-laço"})


def test_encerra_mesmo_com_except_solto_como_o_da_biblioteca():
    never = []

    def spin():  # igual ao start_websocket da biblioteca
        while True:
            try:
                if never:
                    return 1
            except:  # noqa: E722
                pass
            pass

    def retry():  # igual ao get_candles: o except engole a primeira e chama self.connect(), que demora
        while True:
            try:
                while not never:
                    pass
            except:  # noqa: E722
                time.sleep(0.8)  # a próxima exceção cai aqui, fora do try, e encerra a thread

    for name, fn in (("solto", spin), ("repete", retry)):
        with pytest.raises(BrokerError):
            call_with_deadline(name, fn, timeout=0.05)
    assert wait_gone({"iq-solto", "iq-repete"})


def test_chamada_presa_na_rede_conta_ate_sair():
    release = threading.Event()
    before = stuck_calls()
    with pytest.raises(BrokerError):
        call_with_deadline("rede", release.wait, timeout=0.05)  # esperando em C: a exceção só entra quando voltar
    assert stuck_calls() == before + 1
    release.set()
    assert wait_gone({"iq-rede"})
    assert stuck_calls() == before


def iq_stub(on_connect=None, alive=True, now=None):
    """Imitação do objeto IQ_Option da biblioteca (só o que o adaptador usa)."""
    state = SimpleNamespace(closed=False)

    def close():
        state.closed = True

    inner = SimpleNamespace(close=close, websocket_alive=lambda: alive)
    return SimpleNamespace(
        api=inner, state=state,
        connect=on_connect or (lambda: (True, None)),
        change_balance=lambda mode: None,
        get_server_timestamp=now or time.time,
        get_all_init_v2=lambda: {},
    )


def test_conexao_morta_e_percebida_sem_depender_da_bandeira_global():
    b = IQOptionBroker("a@b.c", "x")
    assert b.is_connected() is False
    b._api = iq_stub()
    b._skew = 0.0
    assert b.is_connected() is True
    b._api = iq_stub(alive=False)  # websocket caiu
    assert b.is_connected() is False
    b._api = iq_stub(now=lambda: time.time() - CLOCK_FROZEN_SECONDS - 5)  # websocket "de pé", mas o horário parou
    assert b.is_connected() is False
    b._skew = -29.0  # relógio do computador atrasado 29 s: não é conexão morta
    b._api = iq_stub(now=lambda: time.time() + 29)
    assert b.is_connected() is True


def test_conexao_cheia_de_chamadas_presas_nao_abre_mais_threads(monkeypatch):
    b = IQOptionBroker("a@b.c", "x")
    b._api = iq_stub()
    monkeypatch.setattr("app.broker.iqoption.stuck_calls", lambda: MAX_STUCK_CALLS)
    with pytest.raises(BrokerError, match="presas"):
        b.server_time()


def test_login_limpa_a_sessao_guardada(monkeypatch):
    pytest.importorskip("iqoptionapi")
    from iqoptionapi import global_value

    seen = {}
    fake = iq_stub(on_connect=lambda: (seen.update(ssid=global_value.SSID), (True, None))[1])
    monkeypatch.setattr("iqoptionapi.stable_api.IQ_Option", lambda email, password: fake)
    monkeypatch.setattr(global_value, "SSID", "sessao-vencida")
    b = IQOptionBroker("a@b.c", "x")
    b.connect()
    assert seen["ssid"] is None  # com a sessão velha, o login da biblioteca fica esperando para sempre
    assert b.is_connected()
    b.disconnect()
    assert fake.state.closed and b._api is None


def test_login_que_falha_nao_deixa_meia_conexao(monkeypatch):
    pytest.importorskip("iqoptionapi")
    fake = iq_stub(on_connect=lambda: (False, '{"code":"invalid_credentials"}'))
    monkeypatch.setattr("iqoptionapi.stable_api.IQ_Option", lambda email, password: fake)
    b = IQOptionBroker("a@b.c", "x")
    with pytest.raises(BrokerError, match="recusou o e-mail ou a senha"):
        b.connect()
    assert fake.state.closed and b._api is None


def test_historico_sem_o_laco_da_biblioteca():
    pytest.importorskip("iqoptionapi")
    from iqoptionapi import constants as op_code

    asked = {}
    candles = SimpleNamespace(candles_data=None)

    def getcandles(active, tf, count, end):
        asked.update(active=active, tf=tf, count=count, end=end)
        candles.candles_data = [{"from": 60, "open": 1, "max": 2, "min": 0.5, "close": 1.5}]

    b = IQOptionBroker("a@b.c", "x")
    b._api = SimpleNamespace(api=SimpleNamespace(candles=candles, getcandles=getcandles))
    out = b._request_candles("EURUSD", 60, 1, 120)
    assert out[0]["from"] == 60
    assert asked == {"active": op_code.ACTIVES["EURUSD"], "tf": 60, "count": 1, "end": 120}
