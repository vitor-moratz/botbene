from app.strategies.base import Direction
from app.strategies.ldp_v13 import LdpV13
from app.strategies.wiki_pro_v21 import WikiProV21
from tests.helpers import random_walk, seq

LDP_SCENARIO = seq(
    (11.0, 11.1, 10.6, 10.7),  # 0 vermelha
    (10.7, 10.8, 10.3, 10.4),  # 1 vermelha
    (10.4, 10.5, 10.0, 10.1),  # 2 vermelha
    (10.0, 11.0, 10.0, 11.0),  # 3 comando de alta (careca) depois de vermelha -> linha verde 10.5
    (11.0, 11.5, 10.9, 11.4),  # 4 verde, não toca a linha
    (10.7, 11.0, 10.4, 10.9),  # 5 verde que toca 10.5 e fecha acima -> CALL reteste
    (10.9, 10.95, 10.2, 10.3),  # 6 vermelha fecha abaixo da linha -> PUT rompimento
)


def test_ldp_v13_linha_verde_e_50_do_ultimo_comando_fechado():
    res = LdpV13().analyze(LDP_SCENARIO)
    assert res.buy_line[3] is None  # a própria vela de comando ainda não tem linha
    assert res.buy_line[4] == 10.5
    assert res.sell_line[6] is None


def test_ldp_v13_call_reteste_e_put_rompimento():
    signals = LdpV13().scan(LDP_SCENARIO)
    assert [s.index for s in signals if s] == [5, 6]
    assert signals[5].direction is Direction.CALL and signals[5].setup == "reteste"
    assert signals[6].direction is Direction.PUT and signals[6].setup == "rompimento"


def test_wiki_pro_v21_sinais_coerentes_com_a_vela():
    candles = random_walk(600, seed=3)
    signals = [s for s in WikiProV21().scan(candles) if s]
    assert signals, "esperava ao menos um sinal no histórico sintético"
    for s in signals:
        c = candles[s.index]
        assert s.details["score"] >= 3
        assert (c.close > c.open) if s.direction is Direction.CALL else (c.close < c.open)


def test_wiki_pro_v21_nao_sinaliza_durante_aquecimento():
    # ADX = rma(dx, 14) sobre dx, que já depende de rma(14): primeiro valor na vela 2*14-2 = 26.
    candles = random_walk(600, seed=3)
    signals = WikiProV21().scan(candles)
    assert all(s is None for s in signals[:26])
