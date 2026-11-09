"""Troca automática entre OTC e mercado normal.

Na IQ, o mesmo par existe na binária do mercado normal ("EURUSD-op") e no OTC ("EURUSD-OTC"). O OTC fica
aberto quando o normal fecha (fim de semana, à noite). Com a troca ligada, o bot opera o normal sempre que
ele está aberto e volta para o OTC quando ele fecha.

Só decide para onde ir, a partir da lista de pares da corretora (`Broker.pairs()`): quem troca é o bot.
"""

from __future__ import annotations

from app.market.candle import is_otc, twin_asset

# Não troca para um mercado que fecha em menos que isso, nem sai do normal se ele volta a abrir antes disso:
# cada troca recarrega o par, e ficar indo e voltando por causa de uma pausa curta só atrapalha.
SWITCH_MARGIN_SECONDS = 30 * 60
TO_NORMAL, TO_OTC = "normal", "otc"


def _usable(p: dict | None, now: float, min_payout: float | None, margin: float) -> bool:
    """Aberto para binária agora, sem fechar logo e com payout que passa no mínimo da Configuração."""
    if not p or not p.get("open"):
        return False
    closes = p.get("next_close")
    if closes is not None and closes - now <= margin:
        return False
    payout = p.get("payout")
    return min_payout is None or payout is None or payout >= min_payout - 1e-9


def market_target(asset: str, pairs: dict[str, dict], now: float, min_payout: float | None = None,
                  margin: float = SWITCH_MARGIN_SECONDS) -> tuple[str, str] | None:
    """Para qual par trocar `asset` agora, e por quê (TO_NORMAL ou TO_OTC). None = fica onde está.

    - No OTC: vai para o normal quando ele abre (e o payout dele passa no mínimo).
    - No normal: volta para o OTC só quando o normal fecha de verdade (não numa pausa curta)."""
    other = twin_asset(asset)
    if other is None:
        return None
    if is_otc(asset):
        return (other, TO_NORMAL) if _usable(pairs.get(other), now, min_payout, margin) else None
    normal = pairs.get(asset)
    if normal is not None and normal.get("open"):
        return None
    reopens = normal.get("next_open") if normal else None
    if reopens is not None and reopens - now <= margin:
        return None
    return (other, TO_OTC) if _usable(pairs.get(other), now, min_payout, margin) else None
