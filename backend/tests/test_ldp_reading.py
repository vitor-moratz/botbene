"""Leitura do estudo: lotes, nova alta/baixa + nova posição, indecisão e regiões (figuras das págs. 106-135)."""

import pytest

from app.ldp.engine import LdpEngine
from app.ldp.reading import ReadingEngine, read_candles
from app.market.candle import Candle
from tests.helpers import random_walk, seq

G = (10.0, 10.3, 9.9, 10.2)  # verde com pavio dos dois lados


def green(o, c, up=0.1, down=0.1):
    return (o, c + up, o - down, c)


def red(o, c, up=0.1, down=0.1):
    return (o, o + up, c - down, c)


def lots_of(*ohlc):
    return read_candles(seq(*ohlc))[1]


def codes(reading, code):
    return [t.index for t in reading.tags if t.code == code]


# ---------------------------------------------------------------- lote


def test_lote_sao_velas_da_mesma_cor_pag121():
    reading = lots_of(red(11, 10.8), green(10.8, 11), green(11, 11.2), green(11.2, 11.4), red(11.4, 11.2), red(11.2, 11))
    buy, sell = reading.lots
    assert (buy.direction, buy.start, buy.end) == (1, 1, 3)
    assert (sell.direction, sell.start, sell.end) == (-1, 4, 5)


def test_uma_vela_de_outra_cor_que_nao_rompe_vira_nano_lote_e_nao_fecha_o_lote_pag126_e_182():
    reading = lots_of(green(10, 10.2), red(10.2, 10.0), red(10, 9.8), green(9.8, 9.9), red(9.9, 9.6), red(9.6, 9.4))
    sell = reading.lots[-1]
    assert (sell.direction, sell.start, sell.end) == (-1, 1, 5) and sell.closed_at is None
    assert codes(reading, "NL") == [3]
    region = next(r for r in reading.regions if r.code == "NL")
    assert (region.low, region.high, region.side) == (9.8, 9.9, -1)  # corpo da vela isolada; a leitura segue o lote


def test_reversao_confirmada_fecha_o_lote_e_abre_o_outro_pag123():
    reading = lots_of(green(10, 10.2), green(10.2, 10.4), red(10.4, 10.3), red(10.3, 10.25))
    buy, sell = reading.lots
    assert buy.close_cause == "reversao" and sell.open_cause == "reversao" and sell.start == 2


def test_corpo_que_passa_da_vela_que_abriu_o_lote_e_rompimento_pag115_e_123():
    reading = lots_of(green(10, 10.2), green(10.2, 10.4), red(10.4, 9.8))
    assert reading.lots[0].close_cause == "rompimento" and reading.lots[0].closed_at == 2


def test_so_o_pavio_passar_da_abertura_nao_rompe_pag115():
    reading = lots_of(green(10, 10.2), green(10.2, 10.4), (10.4, 10.5, 9.5, 10.1))
    assert reading.lots[0].close_cause is None


def test_fim_de_taxa_fecha_o_lote_e_se_o_fluxo_seguir_abre_outro_pag122_e_123():
    expirado = (10.2, 10.4, 10.1, 10.4)  # pavio na abertura, careca no fechamento
    reading = lots_of(green(10, 10.2), expirado, green(10.4, 10.6), green(10.6, 10.8))
    first, second = reading.lots
    assert first.close_cause == "fim_de_taxa" and second.open_cause == "fim_de_taxa" and second.start == 2


def test_doji_nao_fecha_o_lote():
    reading = lots_of(green(10, 10.2), green(10.2, 10.4), (10.4, 10.5, 10.3, 10.4), green(10.4, 10.6))
    assert len(reading.lots) == 1 and reading.lots[0].end == 3


# ---------------------------------------------------------------- nova alta/baixa + nova posição


FIG_129 = (red(11, 10.6, 0.1, 0.1), green(10.6, 10.8), green(10.8, 11.2, 0.1), green(11.2, 11.5, 0.1, 0.1), red(11.5, 11.3))


def test_nova_alta_e_a_vela_que_rompe_a_maxima_anterior_e_a_seguinte_e_a_nova_posicao_pag129():
    reading = lots_of(*FIG_129)
    assert codes(reading, "NA") == [2]  # a vela 2 do lote não passou da máxima da vermelha; a 3 passou
    assert codes(reading, "NP") == [3]


def test_regiao_vai_da_projecao_da_nova_posicao_ao_pavio_da_nova_alta_pag102():
    reading = lots_of(*FIG_129)
    region = next(r for r in reading.regions if r.code == "NA")
    assert region.side == 1 and region.label == "Nova alta + nova posição"
    assert region.high == pytest.approx(11.3)  # pavio da nova alta
    assert region.low == pytest.approx(11.1)  # projeção de baixa da nova posição


def test_nova_posicao_sem_pavio_marca_a_abertura_pag130():
    reading = lots_of(red(11, 10.6), green(10.6, 10.8), green(10.8, 11.2, 0.1), (11.2, 11.6, 11.2, 11.5), red(11.5, 11.3))
    region = next(r for r in reading.regions if r.code == "NA")
    assert region.low == 11.2  # fechamento da nova alta, igual à abertura da nova posição


def test_sem_pavio_no_rompimento_vale_o_primeiro_pavio_depois_pag102():
    careca = (10.8, 11.2, 10.7, 11.2)  # rompe sem deixar pavio em cima
    reading = lots_of(red(11, 10.6), green(10.6, 10.8), careca, green(11.2, 11.5, 0.1), green(11.5, 11.7), red(11.7, 11.5))
    assert codes(reading, "NA") == [3] and codes(reading, "NP") == [4]


def test_nova_baixa_espelha_pag102():
    reading = lots_of(green(10, 10.4), red(10.4, 10.2), red(10.2, 9.8), red(9.8, 9.5), green(9.5, 9.6))
    assert codes(reading, "NB") == [2] and codes(reading, "NP") == [3]
    region = next(r for r in reading.regions if r.code == "NB")
    assert region.side == -1  # do pavio da nova baixa até a projeção
    assert (region.low, region.high) == (pytest.approx(9.7), pytest.approx(9.9))


def test_regiao_de_lote_antigo_sai_da_leitura():
    moves = []
    price = 10.0
    for _ in range(4):  # lotes alternados, rompendo o anterior
        moves += [green(price, price + 0.5), green(price + 0.5, price + 1.0)]
        price += 1.0
        moves += [red(price, price - 0.3), red(price - 0.3, price - 0.6)]
        price -= 0.6
    reading = lots_of(*moves)
    live_lots = {r.lot_id for r in reading.active_regions() if r.lot_id is not None}
    newest = {lot.id for lot in reading.lots[-4:]}
    assert live_lots <= newest


# ---------------------------------------------------------------- indecisão


DUPLA = ((10, 11.5, 9.9, 11), (11, 11.4, 10.9, 11.3))


def test_indecisao_exige_o_corpo_inteiro_dentro_do_pavio_pag106():
    assert codes(lots_of(*DUPLA), "DP") == [1]
    corpo_grande = (10.6, 11.4, 10.5, 11.3)  # fecha dentro do pavio, mas o corpo começa bem abaixo dele
    assert codes(lots_of(DUPLA[0], corpo_grande), "DP") == []


def test_indecisao_marca_pavios_e_fracionamento_e_rompida_ganha_o_lado_de_quem_rompeu_pag106_e_110():
    reading = lots_of(*DUPLA, (11.3, 11.9, 11.25, 11.8))
    region = next(r for r in reading.regions if r.code == "DP")
    assert (region.low, region.high) == (11, 11.5)
    assert region.side == 1 and region.resolved == 2 and region.active


def test_indecisao_rompida_para_baixo_vira_regiao_de_venda():
    reading = lots_of(*DUPLA, red(11.3, 10.6))
    region = next(r for r in reading.regions if r.code == "DP")
    assert region.side == -1 and region.resolved == 2


# ---------------------------------------------------------------- vela de força e defesas


def vd(reading):
    return [t for t in reading.tags if t.code == "VD"]


CALMA = ((10.2, 10.3, 10.1, 10.25), (10.25, 10.32, 10.12, 10.18)) * 3  # velas de 0,2: a "vela média"
# comando único de alta (abertura 10.18, 50% 10.54) + uma vela do lote
COMANDO_E_LOTE = (*CALMA, (10.18, 11.0, 10.18, 10.9), (10.9, 11.1, 10.85, 11.05))
VF_NA_DEFESA = (11.05, 11.15, 10.3, 10.45)  # vermelha com pavio dos dois lados, 4× a vela média, fecha na região do comando


def test_vela_de_forca_que_para_na_abertura_do_comando_vira_a_leitura_pag218():
    reading = lots_of(*COMANDO_E_LOTE, VF_NA_DEFESA)
    [tag] = vd(reading)
    assert tag.index == 8 and tag.direction == 1 and "comando" in tag.detail  # a força era de venda: a leitura vira CALL
    assert codes(reading, "VF") == [8]


def test_vela_de_forca_que_rompe_a_defesa_nao_e_vela_na_defesa_pag115():
    assert vd(lots_of(*COMANDO_E_LOTE, (11.05, 11.15, 9.8, 9.9))) == []


def test_vela_que_nao_e_de_forca_nao_conta_mesmo_parando_na_defesa():
    comando_vermelho = (11.05, 11.05, 10.3, 10.45)  # careca na abertura: é comando, não vela de força (pág. 11)
    assert vd(lots_of(*COMANDO_E_LOTE, comando_vermelho)) == []


def test_vela_de_forca_pequena_nao_e_vela_de_forca_pag11():
    pequena = (10.25, 10.3, 10.1, 10.15)  # pavio dos dois lados, mas do tamanho das outras: não é impulso
    assert codes(lots_of(*CALMA, pequena), "VF") == []


def test_primeiro_candle_da_reversao_confirmada_vira_defesa_pag151():
    reading = lots_of(green(10, 10.4), red(10.4, 10.2), red(10.2, 10.0))
    assert codes(reading, "DF") == [1]
    region = next(r for r in reading.regions if r.code == "DF")
    assert region.side == -1 and region.low == pytest.approx(10.2) and region.high == pytest.approx(10.4)


def test_reversao_fora_de_topo_ou_fundo_nao_vira_defesa_pag149():
    # duas reversões de baixa confirmadas; só a primeira nasceu no topo das últimas velas
    reading = lots_of(green(10, 11), red(11, 10.6), red(10.6, 10.3), green(10.3, 10.6), red(10.6, 10.5), red(10.5, 10.4))
    assert codes(reading, "DF") == [1]


# ---------------------------------------------------------------- regiões


def test_regiao_rompida_com_corpo_sai_da_leitura_e_com_pavio_nao_pag115():
    base = FIG_129[:4]
    so_pavio = lots_of(*base, (11.5, 11.6, 10.0, 11.4))
    assert next(r for r in so_pavio.regions if r.code == "NA").active
    com_corpo = lots_of(*base, red(11.5, 10.5))
    assert next(r for r in com_corpo.regions if r.code == "NA").broken == 4


def test_lote_longo_nao_acumula_regioes_mas_mantem_a_central_e_a_indecisao_pag110_e_162():
    candles = random_walk(600, seed=3)
    engine = LdpEngine()
    reading = ReadingEngine()
    for c in candles:
        reading.process(engine.process(c), engine)
        by_lot = {}
        for r in reading.active_regions():
            if r.lot_id is not None and r.code not in ("NA", "NB", "DP", "TP", "FA", "FB"):
                by_lot[r.lot_id] = by_lot.get(r.lot_id, 0) + 1
        assert all(n <= reading.cfg.max_other_per_lot for n in by_lot.values())


def test_nunca_passa_do_limite_de_regioes_ativas():
    candles = random_walk(600, seed=3)
    engine = LdpEngine()
    reading = ReadingEngine()
    for c in candles:
        reading.process(engine.process(c), engine)
        assert len(reading.active_regions()) <= reading.cfg.max_active_regions


# ---------------------------------------------------------------- transferência e desinstalação


def test_pavios_alinhados_na_mesma_cor_sao_transferencia_pag134():
    # velas 0 e 2 verdes, com o pavio de cima na mesma altura; a do meio não passa dele
    candles = (green(10, 10.5, 0.5), green(10.5, 10.6, 0.1), green(10.6, 10.8, 0.2), red(10.8, 10.6, 0.05))
    assert codes(lots_of(*candles), "TR") == [2]


def test_pavios_alinhados_em_cores_diferentes_sao_desinstalacao_pag135():
    candles = (green(10, 10.5, 0.5), green(10.5, 10.6, 0.1), red(10.6, 10.5, 0.4), red(10.5, 10.4, 0.05))
    assert codes(lots_of(*candles), "DS") == [2]


def test_sem_alinhamento_nao_ha_transferencia():
    candles = (green(10, 10.5, 0.5), green(10.5, 10.6, 0.1), green(10.6, 10.8, 0.7))
    reading = lots_of(*candles)
    assert codes(reading, "TR") == [] and codes(reading, "DS") == []


# ---------------------------------------------------------------- cenário


def trend(n=60, step=0.5):
    return [Candle(ts=60 * i, open=10 + i * step, high=10 + (i + 1) * step + 0.05, low=10 + i * step - 0.05, close=10 + (i + 1) * step) for i in range(n)]


def test_movimento_direcional_e_tendencia_pag223():
    assert read_candles(trend())[1].scenarios[-1] == "tendencia"


def test_preco_parado_depois_de_andar_e_consolidado_pag223():
    flat = [Candle(ts=60 * (60 + i), open=40.0, high=40.05, low=39.95, close=40.0 + (0.01 if i % 2 else -0.01)) for i in range(15)]
    assert read_candles(trend() + flat)[1].scenarios[-1] == "consolidacao"


def test_vai_e_vem_com_amplitude_e_topos_e_fundos_pag223():
    candles = []
    price = 10.0
    for i in range(80):
        move = 1.0 if (i // 4) % 2 == 0 else -1.0
        candles.append(Candle(ts=60 * i, open=price, high=max(price, price + move) + 0.1, low=min(price, price + move) - 0.1, close=price + move))
        price += move
    assert read_candles(candles)[1].scenarios[-1] == "topos_fundos"


def test_poucas_velas_ainda_nao_tem_cenario():
    assert read_candles(trend(5))[1].scenarios[-1] is None


# ---------------------------------------------------------------- sem repintura


def test_o_que_foi_lido_numa_vela_nao_muda_com_as_velas_seguintes():
    candles = random_walk(400, seed=11)
    full = read_candles(candles)[1]
    for cut in (60, 150, 280):
        partial = read_candles(candles[:cut])[1]
        assert partial.tags == [t for t in full.tags if t.confirmed < cut]
        assert partial.scenarios == full.scenarios[:cut]
        for lot in partial.lots:
            other = full.lots[lot.id - 1]
            assert (lot.direction, lot.start, lot.open_cause) == (other.direction, other.start, other.open_cause)
