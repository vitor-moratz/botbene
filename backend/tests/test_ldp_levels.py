"""Mapa de níveis: papel pela posição, defesa por pavio, rompimento só com corpo e inversão (pág. 95, 115, 148)."""

from app.ldp.engine import LdpEngine
from app.ldp.levels import Role
from tests.helpers import seq


def level_at(engine, price):
    found = [lv for lv in engine.levels._levels if abs(lv.price - price) < 1e-9]
    assert found, f"nível {price} não existe"
    return found[0]


def test_comando_de_alta_cria_suportes():
    engine = LdpEngine()
    engine.run(seq((10, 12.5, 10, 12)))  # comando único de alta: abertura 10 e 50% 11
    assert level_at(engine, 10).role is Role.SUPPORT
    assert level_at(engine, 11).role is Role.SUPPORT


def test_pavio_que_toca_e_volta_e_defesa_nao_rompimento():
    engine = LdpEngine()
    engine.run(seq((10, 12.5, 10, 12), (12, 12.3, 10.8, 11.9)))  # pavio desce até 10.8, corpo fecha acima de 11
    lv = level_at(engine, 11)
    assert lv.role is Role.SUPPORT and lv.active and lv.touches == 1


def test_corpo_fechando_abaixo_inverte_o_papel_e_segundo_rompimento_desativa():
    engine = LdpEngine()
    engine.run(seq((10, 12.5, 10, 12), (12, 12.1, 10.4, 10.5)))  # fecha abaixo de 11
    lv = level_at(engine, 11)
    assert lv.role is Role.RESISTANCE and lv.flipped  # suporte rompido vira resistência
    engine.process(seq((10.5, 11.6, 10.4, 11.5), start_ts=10_000)[0])  # fecha acima de novo
    assert not lv.active


def test_zona_suporte_e_resistencia_mais_proximos():
    engine = LdpEngine()
    engine.run(seq((10, 12.5, 10, 12)))
    zone = engine.levels.zone(11.5)
    assert zone.support.price == 11
    assert zone.room_down == 0.5


def test_marcacoes_proximas_viram_um_nivel_mais_forte():
    engine = LdpEngine()
    # C1 de alta seguido de C1 de alta: a junção (11) aparece como fechamento e como taxa dividida
    engine.run(seq((10, 11, 10, 11), (11, 12, 11, 12)))
    lv = level_at(engine, 11)
    assert lv.strength == 3
    assert "td_n1:taxa_dividida" in lv.sources
