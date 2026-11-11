"""Desempenho só com ordens enviadas à corretora, em dinheiro (tela Desempenho).

As estatísticas das estratégias (analytics/stats.py) contam as entradas avaliadas, em unidades. Aqui entra só
o que virou ordem e teve resultado (ganhou, perdeu, empate), com o valor de verdade de cada uma. Entrada
manual também conta: é dinheiro da conta. Ordem aberta, não enviada ou sem resultado fica de fora da conta,
mas aparece no total de cada tipo.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from app.market.candle import is_otc
from app.paper import DRAW, LOSS, WIN

RESOLVED = (WIN, LOSS, DRAW)
OPEN = ("enviando", "aberta")
NOT_SENT = ("erro", "bloqueada")
NO_RESULT = "sem_resultado"
MANUAL = "manual"  # o mesmo nome de app.strategies.MANUAL


def _realized_payout(order: dict) -> float | None:
    """Payout que a corretora pagou de fato (só dá para saber nas vitórias)."""
    if order["status"] == WIN and order.get("amount") and order.get("profit") is not None:
        return order["profit"] / order["amount"]
    return None


def order_rows(orders: Iterable[dict], signals: dict[int, dict], default_payout: float) -> list[dict]:
    """Ordens com resultado, em ordem de tempo, no formato que as estatísticas usam.

    `profit` vem em dinheiro. O payout (para o mínimo de empate) é o pago de fato nas vitórias; nas outras,
    o do sinal que gerou a ordem; sem sinal (entrada manual), a média paga nas vitórias."""
    resolved = sorted((o for o in orders if o["status"] in RESOLVED), key=lambda o: (o["requested_at"], o["id"]))
    paid = [p for p in map(_realized_payout, resolved) if p is not None]
    fallback = sum(paid) / len(paid) if paid else default_payout
    rows = []
    for o in resolved:
        sig = signals.get(o["signal_id"]) if o.get("signal_id") else None
        payout = _realized_payout(o) or (sig or {}).get("payout") or fallback
        setup = (sig or {}).get("setup") or ("entrada manual" if o["strategy"] == MANUAL else "—")
        rows.append({"result": o["status"], "profit": o.get("profit") or 0.0, "payout": payout, "entry_ts": o["requested_at"],
                     "strategy": o["strategy"], "setup": setup, "asset": o["asset"], "is_otc": is_otc(o["asset"]),
                     "amount": o["amount"], "option_type": o.get("option_type") or "binary", "gale": o.get("gale") or 0})
    return rows


def cycle_breakeven(stake: float, levels: int, payout: float) -> float:
    """Acerto mínimo na contagem por ciclo (% de ciclos ganhos, a mesma do painel): o ciclo ganho rende ~uma entrada; o
    perdido custa a entrada e todos os gales. Com G2 e payout de 83%: 16,14 ÷ (16,14 + 1,66) = 90,7%."""
    from app.risk import gale_stake
    loss, s = 0.0, stake
    for _ in range(levels + 1):
        loss += s
        s = gale_stake(stake, loss, payout)
    return loss / (loss + stake * payout)


def cycle_limit(stake: float, levels: int, payout: float) -> float:
    """Para empatar, pode perder no máximo 1 ciclo a cada N ciclos (ganhos cobrem o perdido)."""
    from app.risk import gale_stake
    loss, s = 0.0, stake
    for _ in range(levels + 1):
        loss += s
        s = gale_stake(stake, loss, payout)
    return loss / (stake * payout) + 1


def cycle_rows(rows: list[dict], gale_strategies: set[str], levels: int,
               open_tail: bool | Iterable[str] = False) -> list[dict]:
    """As ordens viradas em ciclos de gale (para "contar por ciclo"), com a regra do painel: um ciclo aberto por
    estratégia; a entrada (gale 0) de quem usa o gale abre o ciclo dela e o gale 1, 2… continua. Cada ciclo vira uma
    linha: ganho = 1 vitória, perdido = 1 derrota (% de ciclos ganhos), com o dinheiro do ciclo inteiro e, em `losses`,
    quantas ordens ele perdeu. Ciclo que ficou no meio conta como perdido, a não ser que o bot ainda esteja nele
    (`open_tail`: True para todos, ou as estratégias com ciclo em andamento): aí fica fora. Quem não usa gale passa
    como está."""
    out: list[dict | None] = []
    cycles: dict[str, dict] = {}

    def close(key: str, result: str | None = None) -> None:
        c = cycles.pop(key)
        result = result or (LOSS if c["losses"] else DRAW)
        out[c["slot"]] = dict(c["first"], result=result, profit=round(c["profit"], 2), cycle=True, losses=c["losses"])

    for r in rows:
        key = r["strategy"]
        if key not in gale_strategies and not r.get("gale"):
            out.append(r)
            continue
        cur = cycles.get(key)
        if cur is None and r.get("gale") and len(cycles) == 1:
            key = next(iter(cycles))  # ordens de antes dos ciclos separados: o gale continuava o de outra estratégia
            cur = cycles[key]
        if cur is None or not r.get("gale"):
            if cur is not None:  # a entrada seguinte do gale abriu outro ciclo
                close(key)
            key = r["strategy"]
            cur = cycles[key] = {"first": r, "profit": 0.0, "losses": 0, "slot": len(out)}
            out.append(None)
        cur["profit"] += r.get("profit") or 0.0
        if r["result"] == LOSS:
            cur["losses"] += 1
        if r["result"] == WIN:
            close(key, WIN)
        elif r["result"] == LOSS and (r.get("gale") or 0) >= levels:
            close(key, LOSS)
    running = set(cycles) if open_tail is True else set(open_tail or ())
    for key in list(cycles):
        if key in running:
            cycles.pop(key)  # o bot ainda está nele: fica fora
        else:
            close(key)
    return [r for r in out if r is not None]


def status_counts(orders: Iterable[dict]) -> dict:
    """Quantas ordens estão abertas, não saíram ou ficaram sem resultado (fora da conta do resultado)."""
    counts = Counter(o["status"] for o in orders)
    return {"open": sum(counts[s] for s in OPEN), "not_sent": sum(counts[s] for s in NOT_SENT), "no_result": counts[NO_RESULT]}
