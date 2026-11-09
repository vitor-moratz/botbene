"""Modo paper: avalia cada sinal como se tivesse entrado, sem enviar ordem.

Regra (opção binária de 1 vela): o sinal sai no fechamento da vela k; a entrada é na
ABERTURA da vela k+1 e a saída no FECHAMENTO da vela k+1.
- CALL ganha se fechar acima da entrada; PUT ganha se fechar abaixo; igual = empate.
- Resultado em "entradas": ganho = +payout, perda = -1, empate = 0.
"""

from __future__ import annotations

WIN, LOSS, DRAW, PENDING, CANCELED = "win", "loss", "empate", "pendente", "cancelado"


def judge(direction: str, entry: float, exit_: float) -> str:
    if exit_ == entry:
        return DRAW
    if direction == "call":
        return WIN if exit_ > entry else LOSS
    return WIN if exit_ < entry else LOSS


def profit_units(result: str, payout: float) -> float:
    return {WIN: payout, LOSS: -1.0}.get(result, 0.0)


def order_units(result: str, profit: float | None, amount: float | None) -> float | None:
    """Resultado de uma ordem da corretora em entradas: o payout pago de fato na vitória, -1 na perda, 0 no empate.
    None na vitória sem valor gravado (quem usa cai no payout do sinal)."""
    if result == WIN:
        return round(profit / amount, 4) if profit is not None and amount else None
    return -1.0 if result == LOSS else 0.0
