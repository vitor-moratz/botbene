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
                     "amount": o["amount"], "option_type": o.get("option_type") or "binary"})
    return rows


def status_counts(orders: Iterable[dict]) -> dict:
    """Quantas ordens estão abertas, não saíram ou ficaram sem resultado (fora da conta do resultado)."""
    counts = Counter(o["status"] for o in orders)
    return {"open": sum(counts[s] for s in OPEN), "not_sent": sum(counts[s] for s in NOT_SENT), "no_result": counts[NO_RESULT]}
