"""Qual tipo de opção o bot compra em cada par: binária, digital ou a de maior payout.

Na IQ, a binária e a digital do mesmo par usam o mesmo ativo e o mesmo preço ("EURUSD-OTC", "EURUSD-op"): o
gráfico e as estratégias não mudam, só o produto comprado. O payout da digital muda o tempo todo, por isso o bot
decide a cada vela fechada de cada par (antes de abrir os pedidos da vela seguinte), e a ordem daquela vela sai
no tipo escolhido. Só decide: quem pergunta à corretora e compra é o bot.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.broker.base import BINARY, DIGITAL

BEST = "best"


@dataclass(frozen=True)
class Offer:
    """Um tipo de opção num par agora: dá para comprar? (e por que não) e o payout (None = não sabe)."""

    ok: bool
    why: str
    payout: float | None


@dataclass(frozen=True)
class Choice:
    kind: str
    ok: bool
    why: str
    payout: float | None


def choose(option_type: str, offers: dict[str, Offer]) -> Choice:
    """O tipo da próxima ordem do par.

    - "binary" / "digital": sempre esse tipo (fechado = sem ordem, com o motivo).
    - "best": entre os abertos, o de maior payout; no empate, a binária. Os dois fechados = sem ordem."""
    if option_type in (BINARY, DIGITAL):
        o = offers[option_type]
        return Choice(option_type, o.ok, o.why, o.payout)
    usable = [k for k in (BINARY, DIGITAL) if offers[k].ok]
    if not usable:
        b, d = offers[BINARY], offers[DIGITAL]
        return Choice(BINARY, False, f"{b.why}; {d.why}", b.payout)
    kind = max(usable, key=lambda k: (offers[k].payout if offers[k].payout is not None else -1.0, k == BINARY))
    o = offers[kind]
    return Choice(kind, True, o.why, o.payout)


def _side(p: dict, kind: str) -> dict:
    if kind == DIGITAL:
        return {"open": p.get("digital_open") is True, "payout": p.get("digital_payout"),
                "next_open": p.get("digital_next_open"), "next_close": p.get("digital_next_close")}
    return {"open": bool(p.get("open")), "payout": p.get("payout"),
            "next_open": p.get("next_open"), "next_close": p.get("next_close")}


def market_view(p: dict, option_type: str) -> dict:
    """Um par da lista da corretora visto pelo tipo de opção da Configuração: aberto, payout, quando abre e
    quando fecha. É o que a troca entre OTC e mercado normal (service/market.py) olha."""
    if option_type in (BINARY, DIGITAL):
        return _side(p, option_type)
    sides = [_side(p, BINARY), _side(p, DIGITAL)]
    opened = [s for s in sides if s["open"]]
    if opened:
        payouts = [s["payout"] for s in opened if s["payout"] is not None]
        closes = [s["next_close"] for s in opened]
        return {"open": True, "payout": max(payouts) if payouts else None, "next_open": None,
                "next_close": None if None in closes else max(closes)}  # aberto até o último dos dois fechar
    opens = [s["next_open"] for s in sides if s["next_open"] is not None]
    return {"open": False, "payout": None, "next_open": min(opens) if opens else None, "next_close": None}
