"""Estratégias da leitura do estudo (Etapa 2): retração no lote, reversão A e reversão B."""

from app.ldp.engine import LdpEngine
from app.strategies.base import Direction
from app.strategies.intra import default_intra, plan_all, run_intra
from app.strategies.recipes import (
    RecipeConfig,
    RetracaoLote,
    ReversaoForca,
    ReversaoIndecisao,
)
from tests.helpers import random_walk, seq

CALMA = ((10.2, 10.3, 10.1, 10.25), (10.25, 10.32, 10.12, 10.18)) * 15  # 30 velas de 0,2: aquece e dá a vela média


def plans(recipe, *ohlc):
    engine = LdpEngine()
    return [recipe.on_step(engine.process(c), engine) for c in seq(*ohlc)]


# ---------------------------------------------------------------- reversão A

COMANDO_E_LOTE = ((10.18, 11.0, 10.18, 10.9), (10.9, 11.1, 10.85, 11.05))  # comando único de alta + vela do lote
VF_NA_DEFESA = (11.05, 11.15, 10.3, 10.45)  # vermelha de força desce até a região do comando e fecha nela


def test_reversao_a_entra_contra_a_vela_de_forca_que_travou_na_defesa_pag197_e_218():
    plan = plans(ReversaoForca(), *CALMA, *COMANDO_E_LOTE, VF_NA_DEFESA)[-1]
    [a] = plan.armed
    assert a.direction is Direction.CALL and a.trigger == "reversao" and a.strategy == "reversao_forca"
    assert a.confluences["marcacao"] and a.score >= 2
    assert any("Comando único" in s for s in a.level_sources)
    assert a.target_ts == seq(*CALMA, *COMANDO_E_LOTE, VF_NA_DEFESA)[-1].ts + 60


def test_reversao_a_sem_confluencias_suficientes_nao_arma():
    exigente = ReversaoForca(RecipeConfig(min_confluences=5))
    plan = plans(exigente, *CALMA, *COMANDO_E_LOTE, VF_NA_DEFESA)[-1]
    assert plan.armed == [] and "confluências" in plan.reasons[0]


def test_reversao_a_sem_vela_de_forca_na_defesa_nao_arma():
    comando_vermelho = (11.05, 11.05, 10.3, 10.45)  # comando, não vela de força (pág. 11)
    assert plans(ReversaoForca(), *CALMA, *COMANDO_E_LOTE, comando_vermelho)[-1].armed == []


# ---------------------------------------------------------------- reversão B

INDECISAO = ((10.2, 10.8, 10.15, 10.5), (10.55, 10.7, 10.52, 10.65))  # dupla posição no pavio de cima
ROMPE = (10.65, 11.4, 10.65, 11.3)  # comando de alta fecha acima da indecisão
VOLTA = (11.3, 11.35, 10.9, 10.95)  # recua para perto da região


def test_reversao_b_entra_a_favor_de_quem_rompeu_a_indecisao_na_volta_pag106_e_119():
    *_, rompeu, voltou = plans(ReversaoIndecisao(), *CALMA, *INDECISAO, ROMPE, VOLTA)
    assert rompeu.armed == []  # longe demais da região para uma volta na vela seguinte
    [a] = voltou.armed
    assert a.direction is Direction.CALL and a.trigger == "throwback"
    assert a.level_price == 10.8  # topo da região da dupla posição
    assert any("Dupla posição" in s for s in a.level_sources) and a.score >= 2


def test_reversao_b_exige_forca_ou_comando_no_rompimento():
    fraca = (10.65, 10.85, 10.62, 10.81)  # rompe com o corpo, mas do tamanho de uma vela comum: não é força nem comando
    perto = (10.81, 10.84, 10.79, 10.82)
    assert plans(ReversaoIndecisao(), *CALMA, *INDECISAO, fraca, perto)[-1].armed == []


# ---------------------------------------------------------------- retração no lote

LOTE = ((10.6, 10.7, 10.0, 10.1), (10.1, 10.35, 10.05, 10.3), (10.3, 10.85, 10.25, 10.75), (10.75, 11.0, 10.65, 10.95))
PERTO = (10.95, 11.0, 10.85, 10.9)  # recua até perto da região de nova alta + nova posição


def test_retracao_no_lote_arma_na_regiao_de_nova_alta_mais_nova_posicao_pag162():
    *_, last = plans(RetracaoLote(), *CALMA, *LOTE, PERTO)
    [a] = last.armed
    assert a.direction is Direction.CALL and a.trigger == "retracao" and a.strategy == "retracao_lote"
    assert a.level_sources[0].startswith("Nova alta + nova posição")
    assert a.level_price <= 10.9


# ---------------------------------------------------------------- juntas no bot


def test_as_tres_rodam_juntas_com_uma_leitura_so_por_par():
    candles = random_walk(800, seed=5)
    engine = LdpEngine()
    strategies = [s for s in default_intra() if s.name in ("retracao_lote", "reversao_forca", "reversao_indecisao")]
    armed = 0
    for c in candles:
        step = engine.process(c)
        armed += len(plan_all(strategies, step, engine).armed)
    assert armed > 0
    assert engine.study_reading.last_index == len(candles) - 1


def test_ao_vivo_e_no_historico_armam_igual():
    candles = random_walk(500, seed=8)
    names = ("retracao_lote", "reversao_forca", "reversao_indecisao")
    pick = lambda: [s for s in default_intra() if s.name in names]  # noqa: E731
    _, batch = run_intra(candles, pick())
    _, first = run_intra(candles[:300], pick())
    key = lambda p: [(a.strategy, a.direction, a.level_price, a.target_ts) for a in p.armed]  # noqa: E731
    assert [key(p) for p in first] == [key(p) for p in batch[:300]]
