"""O que aconteceu depois da decisão (o "alvo"), separado dos traços para nunca vazar para eles.

Ficha da operação v0: a decisão sai no fechamento da vela k; a entrada é na ABERTURA de k+1 e o vencimento no
FECHAMENTO de k+1 (1 minuto). CALL ganha se fechar acima da entrada, PUT se fechar abaixo; igual é empate e fica
fora da conta. É a mesma regra da `judge()` do bot (app/paper). A vela k+1 precisa vir logo depois de k, sem
buraco. O resultado em 5 min (fechamento de k+5 contra a abertura de k+1) é só informação.

A abertura da vela é uma aproximação do preço contratado: nas ordens reais do bot ela concordou em 87% dos casos.
"""

from __future__ import annotations

import numpy as np

from app.research.moratz.base import TF, Serie


def proxima(s: Serie) -> tuple[np.ndarray, np.ndarray]:
    """(valida, sobe) para cada k: valida = existe k+1 contínua; sobe = +1 subiu, −1 desceu, 0 empate."""
    n = len(s)
    valida = np.zeros(n, dtype=bool)
    sobe = np.zeros(n, dtype=np.int8)
    if n > 1:
        valida[:-1] = (s.ts[1:] - s.ts[:-1]) == TF
        sobe[:-1] = np.sign(s.c[1:] - s.o[1:])
        sobe[~valida] = 0
    return valida, sobe


def cinco(s: Serie) -> tuple[np.ndarray, np.ndarray]:
    """Só informação: (valida, sobe) no fechamento de k+5 contra a abertura de k+1, com k+1..k+5 contínuas."""
    n = len(s)
    valida = np.zeros(n, dtype=bool)
    sobe = np.zeros(n, dtype=np.int8)
    if n > 5:
        valida[:-5] = (s.ts[5:] - s.ts[:-5]) == 5 * TF
        sobe[:-5] = np.sign(s.c[5:] - s.o[1:-4])
        sobe[~valida] = 0
    return valida, sobe


def resultado(direcao: np.ndarray, sobe: np.ndarray) -> np.ndarray:
    """+1 ganhou, −1 perdeu, 0 empate. `direcao`: +1 CALL, −1 PUT."""
    return (np.asarray(direcao, dtype=np.int8) * np.asarray(sobe, dtype=np.int8)).astype(np.int8)
