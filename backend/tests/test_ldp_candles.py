"""Classificação das velas: figuras das págs. 9, 11, 16, 17 e 24 da apostila."""

from app.ldp.candles import CandleClass as K
from app.ldp.candles import classify
from app.ldp.config import LdpConfig
from app.market.candle import Candle

CFG = LdpConfig()


def cls(o, h, l, c, prev=None):
    prev_list = [prev] if prev else []
    return classify(Candle(0, o, h, l, c), 1, prev_list, CFG)


def test_niveis_de_comando_alta_pag24():
    assert cls(10, 12, 10, 12).cls is K.C1  # careca dos dois lados
    assert cls(10, 12.5, 10, 12).cls is K.C2  # sem pavio na abertura (embaixo)
    assert cls(10, 12, 9.5, 12).cls is K.C3  # sem pavio no fechamento (em cima): expirado


def test_niveis_de_comando_baixa_pag24():
    assert cls(12, 12, 10, 10).cls is K.C1
    assert cls(12, 12, 9.5, 10).cls is K.C2  # sem pavio em cima (abertura da vermelha)
    assert cls(12, 12.5, 10, 10).cls is K.C3  # sem pavio embaixo (fechamento da vermelha)


def test_vela_de_forca_tem_pavio_na_abertura_pag16():
    info = cls(10, 12.5, 9.5, 12)
    assert info.cls is K.FORCA
    assert info.has_open_wick and info.has_close_wick


def test_pavio_dos_dois_lados_com_corpo_pequeno_e_indecisao():
    assert cls(10, 12, 8, 10.6).cls is K.INDECISAO


def test_corpo_enxuto_que_rompe_maxima_anterior_e_vela_de_forca_pag12():
    prev = Candle(0, 10.4, 10.5, 10.0, 10.1)
    assert cls(10, 12, 8, 10.6, prev=prev).cls is K.FORCA


def test_doji():
    assert cls(10, 11, 9, 10.05).cls is K.DOJI
    assert cls(10, 10, 10, 10).cls is K.DOJI


def test_tolerancia_de_pavio():
    # pavio de 1% da amplitude conta como "sem pavio" (tolerância padrão 2%)
    assert cls(10, 12, 9.98, 12).cls is K.C1


def test_gap_pag28():
    prev = Candle(0, 9.0, 10.0, 9.0, 10.0)
    assert cls(10.5, 11.5, 10.5, 11.5, prev=prev).has_gap
    assert not cls(10.0, 11.0, 10.0, 11.0, prev=prev).has_gap


def test_contexto_do_comando_pag6():
    red = Candle(0, 11, 11.1, 10, 10.1)
    assert cls(10.1, 11, 10.1, 10.9, prev=red).cmd_context == "reversao"
    green = Candle(0, 10, 10.5, 9.9, 10.4)
    assert cls(10.4, 11, 10.4, 10.9, prev=green).cmd_context == "rompimento"
    assert cls(10.4, 10.48, 10.4, 10.45, prev=green).cmd_context == "fracionamento"
