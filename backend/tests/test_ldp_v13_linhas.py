from app.strategies.base import Direction
from app.strategies.ldp_v13 import LdpV13
from app.strategies.ldp_v13_linhas import LdpV13Linhas
from tests.helpers import random_walk, seq
from tests.test_strategies import LDP_SCENARIO

# CALL de reteste da linha verde (10.5), mas fechando ABAIXO da linha vermelha (10.9): meio das linhas.
MEIO = seq(
    (11.0, 11.1, 10.6, 10.7),
    (10.7, 10.8, 10.3, 10.4),
    (10.4, 10.5, 10.0, 10.1),
    (10.0, 11.0, 10.0, 11.0),   # 3 comando de alta -> linha verde 10.5
    (11.0, 11.0, 10.75, 10.8),  # 4 comando de baixa -> linha vermelha 10.9
    (10.7, 10.85, 10.4, 10.8),  # 5 CALL reteste no v1.3, mas fecha entre as linhas
)


def test_sinal_no_meio_das_linhas_e_descartado():
    assert [s.index for s in LdpV13().scan(MEIO) if s] == [5]
    assert all(s is None for s in LdpV13Linhas().scan(MEIO))


def test_sinais_do_lado_certo_das_linhas_continuam():
    signals = [s for s in LdpV13Linhas().scan(LDP_SCENARIO) if s]
    assert [(s.index, s.direction) for s in signals] == [(5, Direction.CALL), (6, Direction.PUT)]
    assert signals[0].details["filtro"] == "acima das linhas"


def test_filtro_so_remove_nunca_cria_sinal():
    candles = random_walk(500, seed=9)
    base = LdpV13().scan(candles)
    filtered = LdpV13Linhas().scan(candles)
    for b, f in zip(base, filtered):
        if f is not None:
            assert b is not None and b.direction is f.direction
    assert sum(f is not None for f in filtered) < sum(b is not None for b in base)
