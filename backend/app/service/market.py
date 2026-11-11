"""Troca automática entre OTC e mercado normal.

Na IQ, o mesmo par existe na binária do mercado normal ("EURUSD-op") e no OTC ("EURUSD-OTC"). O OTC fica
aberto quando o normal fecha (fim de semana, à noite). Com a troca ligada, o bot opera o normal sempre que
ele está aberto e volta para o OTC quando ele fecha.

Só decide para onde ir, a partir da lista de pares da corretora (`Broker.pairs()`): quem troca é o bot.

Dois jeitos (Configuração, `market_mode`):
- "por_par": cada par vai para o OTC quando o normal dele fecha e volta quando ele abre;
- "normal_primeiro" (09/11/2026, pedido do usuário): enquanto algum par normal da lista estiver aberto, todos ficam
  no normal (os fechados esperam, sem operar); só quando todos os normais fecham é que todos vão para o OTC.
"""

from __future__ import annotations

from app.market.candle import is_otc, twin_asset

# Não troca para um mercado que fecha em menos que isso, nem sai do normal se ele volta a abrir antes disso:
# cada troca recarrega o par, e ficar indo e voltando por causa de uma pausa curta só atrapalha.
SWITCH_MARGIN_SECONDS = 30 * 60
TO_NORMAL, TO_OTC = "normal", "otc"
MARKET_MODES = ("por_par", "normal_primeiro")


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


def normal_first_targets(assets: list[str], pairs: dict[str, dict], now: float, min_payout: float | None = None,
                         margin: float = SWITCH_MARGIN_SECONDS) -> dict[str, tuple[str, str] | None]:
    """"Normal primeiro": com algum par normal aberto (e sem fechar logo), todos no normal; com todos fechados (e nenhum
    reabrindo em menos de `margin`), todos no OTC. Par sem mercado normal na IQ fica onde está."""
    normals = [pairs.get(a if not is_otc(a) else twin_asset(a)) for a in assets if twin_asset(a)]
    any_open = any(_usable(p, now, min_payout, margin) for p in normals)
    reopening = any(p is not None and not p.get("open") and p.get("next_open") is not None and p["next_open"] - now <= margin
                    for p in normals)
    out: dict[str, tuple[str, str] | None] = {}
    for a in assets:
        other = twin_asset(a)
        if other is None:
            out[a] = None
        elif any_open:
            out[a] = (other, TO_NORMAL) if is_otc(a) and other in pairs else None
        elif reopening:
            out[a] = None
        else:
            out[a] = (other, TO_OTC) if not is_otc(a) and _usable(pairs.get(other), now, min_payout, margin) else None
    return out


def market_targets(assets: list[str], pairs: dict[str, dict], now: float, min_payout: float | None = None,
                   mode: str = "por_par") -> dict[str, tuple[str, str] | None]:
    """Para onde cada par deve ir agora, no jeito escolhido na Configuração."""
    if mode == "normal_primeiro":
        return normal_first_targets(assets, pairs, now, min_payout)
    return {a: market_target(a, pairs, now, min_payout) for a in assets}
