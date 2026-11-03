"""Estruturas e marcações: figuras das págs. 39-43, 50-54, 97-113, 126-130 e 149 da apostila."""

import pytest

from app.ldp.engine import LdpEngine
from tests.helpers import seq


def last_step(*ohlc):
    return LdpEngine().run(seq(*ohlc))[-1]


def find(step, name):
    found = [s for s in step.structures if s.name == name]
    assert found, f"{name} não encontrada; estruturas: {[s.name for s in step.structures]}"
    return found[0]


def prices(structure):
    return sorted(round(m.price, 6) for m in structure.marks)


def test_td_nivel1_cinco_marcacoes_pag41():
    step = last_step((10, 11, 10, 11), (11, 12, 11, 12))
    td = find(step, "td_n1")
    assert td.direction == 1
    assert prices(td) == [10, 10.5, 11, 11.5, 12]


def test_td_nivel2_expirado_mais_vela_de_forca_pag41():
    step = last_step((12, 12.3, 11, 11), (11, 11.2, 9.8, 10))
    td = find(step, "td_n2")
    assert td.direction == -1
    assert prices(td) == [11, 11.2]  # junção + pavio de cima da vela seguinte


def test_td_nivel3_vela_de_forca_mais_comando_unico_pag42():
    step = last_step((10, 11.3, 9.8, 11), (11, 12.4, 11, 12))
    td = find(step, "td_n3")
    assert prices(td) == [11, 11.3]  # abertura do comando único + pavio


def test_td_intermediaria_pag43():
    step = last_step((12, 12.3, 11, 11), (11, 11, 9.7, 10))
    assert prices(find(step, "td_intermediaria")) == [11]


def test_divisao_de_preco_pag54():
    step = last_step((12, 12.2, 10.8, 11), (11, 11.2, 9.8, 10))
    assert find(step, "divisao_preco").direction == -1


def test_taxa_dividida_exige_mesma_cor_e_sem_gap():
    step = last_step((10, 11, 10, 11), (12, 13, 12, 13))  # GAP
    assert not any(s.name.startswith("td_") for s in step.structures)


def test_td_de_topo_nivel1_pag50():
    step = last_step((10, 10.6, 9.9, 10.5), (10.5, 11.1, 10.4, 11), (11, 12, 10.9, 12), (12, 12, 11, 11.2))
    td = find(step, "td_topo_n1")
    assert td.direction == -1
    assert prices(td) == [11.6, 12]


def test_dupla_posicao_pag106():
    step = last_step((10, 11.5, 9.9, 11), (11, 11.4, 10.9, 11.3))
    dp = find(step, "dupla_posicao")
    assert dp.detail == "superior"
    assert prices(dp) == [11, 11.4, 11.5]  # pavios + fracionamento


def test_futuro_de_alta_pag108():
    step = last_step((10, 11.5, 9.9, 11), (11, 11.8, 10.9, 11.3))
    assert find(step, "futuro_alta").detail == "superior"


def test_tripla_posicao_pag111():
    step = last_step((10, 11.5, 9.9, 11), (11, 11.4, 10.9, 11.3), (11.3, 11.38, 11.25, 11.35))
    assert find(step, "tripla_posicao").detail == "superior"


def test_nova_posicao_rompendo_indecisao_pag108():
    step = last_step((10, 11.5, 9.9, 11), (11, 11.4, 10.9, 11.3), (11.3, 11.9, 11.25, 11.8))
    np_ = find(step, "nova_posicao")
    assert np_.direction == 1 and np_.detail == "rompeu_indecisao"


BASE = ((10.2, 10.5, 10.0, 10.1), (10.1, 10.4, 10.0, 10.3), (10.3, 10.5, 10.1, 10.2), (10.2, 10.4, 10.0, 10.1), (10.1, 10.3, 10.0, 10.2))


def test_nova_alta_e_nova_posicao_pag97_e_113():
    steps = LdpEngine().run(seq(*BASE, (10.2, 11.2, 10.1, 11.0), (11.0, 11.6, 10.8, 11.5)))
    nova_alta = find(steps[-2], "nova_alta")
    assert nova_alta.detail == "rompimento"
    assert prices(nova_alta) == [11.0, 11.2]  # pavio + fechamento
    np_ = find(steps[-1], "nova_posicao")
    assert np_.detail == "apos_nova_alta"
    assert prices(np_) == [10.8]  # projeção de baixa


def test_nova_posicao_comando_unico_marca_abertura_pag130():
    steps = LdpEngine().run(seq(*BASE, (10.2, 11.2, 10.1, 11.0), (11.0, 11.6, 11.0, 11.5)))
    assert prices(find(steps[-1], "nova_posicao")) == [11.0]


def test_rompimento_so_com_corpo_pag115():
    # pavio passa da máxima, mas o corpo fecha dentro: não é nova alta
    step = LdpEngine().run(seq(*BASE, (10.2, 11.2, 10.1, 10.45)))[-1]
    assert not any(s.name == "nova_alta" for s in step.structures)


def test_nano_lote_pag130():
    step = last_step((12, 12.1, 11, 11.2), (11.2, 11.3, 10.5, 10.6), (10.6, 11.0, 10.5, 10.9), (10.9, 11.0, 10.0, 10.1))
    nano = find(step, "nano_lote")
    assert nano.direction == -1
    assert prices(nano) == [10.6, 10.9]  # corpo da vela verde isolada


def test_defesa_primeiro_candle_da_reversao_pag149():
    # 1º candle vermelho sem pavio em cima (comando único): marca o corpo
    step = last_step((10, 11, 9.9, 10.9), (10.9, 10.9, 10.3, 10.4), (10.4, 10.5, 9.8, 9.9))
    defesa = find(step, "defesa")
    assert defesa.direction == -1
    assert prices(defesa) == [10.4, 10.9]  # abertura e fechamento do 1º candle vermelho


def test_defesa_em_vela_de_forca_marca_tambem_50_pag152():
    step = last_step((10, 11, 9.9, 10.9), (10.9, 11.0, 10.3, 10.4), (10.4, 10.5, 9.8, 9.9))
    assert prices(find(step, "defesa")) == [10.4, 10.65, 10.9]


@pytest.mark.parametrize("name", ["comando_n1", "comando_unico", "expirado"])
def test_marcacoes_por_nivel_de_comando_pag26_27(name):
    ohlc = {"comando_n1": (10, 12, 10, 12), "comando_unico": (10, 12.5, 10, 12), "expirado": (10, 12, 9.5, 12)}[name]
    expected = {"comando_n1": [10, 11, 12], "comando_unico": [10, 11], "expirado": [11, 12]}[name]
    step = last_step(ohlc)
    assert prices(find(step, name)) == expected
