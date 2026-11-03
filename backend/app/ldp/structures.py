"""Estruturas da apostila e as marcações que cada uma gera.

Cada estrutura sai com a página da apostila e as marcações (preço + tipo + força 1..3).
A força é um peso inicial ("os pontos fortes de defesa são as aberturas", pág. 149) que
depois será calibrado pelas estatísticas reais.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.ldp.candles import CandleClass as K
from app.ldp.candles import CandleInfo
from app.ldp.config import LdpConfig
from app.market.candle import Candle


@dataclass(frozen=True, slots=True)
class Mark:
    price: float
    kind: str
    strength: int  # 1 fraca, 2 média, 3 forte


@dataclass(frozen=True, slots=True)
class Structure:
    name: str
    index: int  # vela em que a estrutura ficou conhecida (confirmação)
    ref_index: int  # vela principal da estrutura (pode ser anterior à confirmação)
    direction: int  # +1 alta, -1 baixa, 0 neutra/indecisão
    marks: tuple[Mark, ...]
    page: int
    detail: str = ""


def candle_marks(info: CandleInfo, cfg: LdpConfig) -> list[Structure]:
    """Marcações da própria vela: comandos C1/C2/C3 (pág. 26-27), vela de força e pavio grande (pág. 138)."""
    c = info.candle
    i = info.index
    out: list[Structure] = []
    ctx = info.cmd_context or ""
    if info.cls is K.C1:
        marks = (Mark(c.open, "abertura", 3), Mark(c.mid, "50%", 2), Mark(c.close, "fechamento", 2))
        out.append(Structure("comando_n1", i, i, info.direction, marks, 26, ctx))
    elif info.cls is K.C2:
        marks = (Mark(c.open, "abertura", 3), Mark(c.mid, "50%", 2))
        out.append(Structure("comando_unico", i, i, info.direction, marks, 26, ctx))
    elif info.cls is K.C3:
        marks = (Mark(c.mid, "50%", 2), Mark(c.close, "fechamento", 2))
        out.append(Structure("expirado", i, i, info.direction, marks, 27))
    elif info.cls is K.FORCA:
        marks = (Mark(c.open, "abertura", 2), Mark(c.mid, "50%", 1), Mark(c.close, "fechamento", 1))
        out.append(Structure("vela_de_forca", i, i, info.direction, marks, 138))

    if c.range > 0:
        if c.upper_wick >= c.range * cfg.big_wick_pct:
            marks = (Mark(c.high, "ponta_pavio", 1), Mark(c.body_top + c.upper_wick / 2, "50%_pavio", 1))
            out.append(Structure("pavio_grande", i, i, -1, marks, 143, "superior"))
        if c.lower_wick >= c.range * cfg.big_wick_pct:
            marks = (Mark(c.low, "ponta_pavio", 1), Mark(c.body_bottom - c.lower_wick / 2, "50%_pavio", 1))
            out.append(Structure("pavio_grande", i, i, 1, marks, 143, "inferior"))
    return out


def taxa_dividida(a: CandleInfo, b: CandleInfo) -> list[Structure]:
    """Taxa dividida entre duas velas seguidas da mesma cor, sem GAP (pág. 33-43, 54).

    Níveis (pág. 39-40): N1 = C1+C1; N2 = expirado + vela de força; N3 = vela de força +
    comando único (ou vice-versa); intermediária = expirado + comando único.
    Duas velas de força seguidas = divisão de preço (pág. 54).
    """
    if a.direction == 0 or a.direction != b.direction or b.has_gap:
        return []
    d = a.direction
    ca, cb = a.candle, b.candle
    junction = cb.open
    pair = (a.cls, b.cls)
    i, r = b.index, a.index

    if pair == (K.C1, K.C1):
        marks = (
            Mark(ca.open, "defesa_abertura", 3),
            Mark(ca.mid, "50%", 2),
            Mark(junction, "taxa_dividida", 3),
            Mark(cb.mid, "50%", 2),
            Mark(cb.close, "defesa_fechamento", 3),
        )
        return [Structure("td_n1", i, r, d, marks, 41)]
    if pair == (K.C3, K.FORCA):
        marks = (Mark(junction, "taxa_dividida", 3), Mark(b.open_wick_tip, "pavio", 2))
        return [Structure("td_n2", i, r, d, marks, 41)]
    if pair in ((K.FORCA, K.C2), (K.C2, K.FORCA)):
        marks_l = [Mark(junction, "taxa_dividida", 3)]
        if a.has_close_wick:
            marks_l.append(Mark(a.close_wick_tip, "pavio", 2))
        if b.has_open_wick:
            marks_l.append(Mark(b.open_wick_tip, "pavio", 2))
        return [Structure("td_n3", i, r, d, tuple(marks_l), 42)]
    if pair == (K.C3, K.C2):
        return [Structure("td_intermediaria", i, r, d, (Mark(junction, "taxa_dividida", 2),), 43)]
    if pair == (K.FORCA, K.FORCA):
        marks = (
            Mark(junction, "divisao_preco", 2),
            Mark(a.close_wick_tip, "pavio", 1),
            Mark(b.open_wick_tip, "pavio", 1),
        )
        return [Structure("divisao_preco", i, r, d, marks, 54)]

    # Força da junção (pág. 37-38): forte = sem pavio nos dois lados da junção.
    clean_a, clean_b = not a.has_close_wick, not b.has_open_wick
    if clean_a and clean_b:
        return [Structure("td_forte", i, r, d, (Mark(junction, "taxa_dividida", 2),), 37)]
    name = "td_media" if (clean_a or clean_b) else "td_fraca"
    return [Structure(name, i, r, d, (), 37)]


def td_topo_fundo(a: CandleInfo, b: CandleInfo, candles: Sequence[Candle], cfg: LdpConfig) -> list[Structure]:
    """Taxa dividida de topo/fundo: reversão entre duas velas de cores opostas no extremo (pág. 50-53).

    N1 = sem pavio na junção; N2 = com pavio. Marca o fracionamento e os 50% (pág. 138, f/g);
    no N2 também a ponta do pavio e o 50% do pavio (pág. 53).
    """
    if a.direction == 0 or b.direction != -a.direction or b.has_gap:
        return []
    lookback = candles[max(0, a.index - cfg.extreme_lookback) : a.index]
    if not lookback:
        return []
    ca, cb = a.candle, b.candle
    if a.direction > 0:
        if ca.high < max(c.high for c in lookback):
            return []
        prefix, direction, tip = "td_topo", -1, max(ca.high, cb.high)
    else:
        if ca.low > min(c.low for c in lookback):
            return []
        prefix, direction, tip = "td_fundo", 1, min(ca.low, cb.low)
    junction = cb.open
    clean = not a.has_close_wick and not b.has_open_wick
    if clean:
        marks = (Mark(junction, "taxa_dividida", 3), Mark(cb.mid, "50%", 2))
        return [Structure(f"{prefix}_n1", b.index, a.index, direction, marks, 52)]
    marks = (
        Mark(junction, "taxa_dividida", 2),
        Mark(cb.mid, "50%", 2),
        Mark(tip, "ponta_pavio", 2),
        Mark((junction + tip) / 2, "50%_pavio", 1),
    )
    return [Structure(f"{prefix}_n2", b.index, a.index, direction, marks, 53)]


def indecisao(a: CandleInfo, b: CandleInfo) -> list[Structure]:
    """Indecisão / dupla posição: o corpo da vela atual fecha dentro do pavio da anterior (pág. 106-110).

    Se a vela atual ainda deixa um pavio além do da anterior, é futuro de alta/baixa (pág. 108).
    Marcações: os pavios + o fracionamento (pág. 110).
    """
    ca, cb = a.candle, b.candle
    if a.has_upper_wick and ca.body_top < cb.close <= ca.high:
        futuro = b.has_upper_wick and cb.high > ca.high
        marks_l = [Mark(ca.high, "pavio", 2), Mark(ca.body_top, "fracionamento", 2)]
        if b.has_upper_wick and cb.high != ca.high:
            marks_l.append(Mark(cb.high, "pavio", 2))
        name = "futuro_alta" if futuro else "dupla_posicao"
        return [Structure(name, b.index, a.index, 0, tuple(marks_l), 108 if futuro else 109, "superior")]
    if a.has_lower_wick and ca.low <= cb.close < ca.body_bottom:
        futuro = b.has_lower_wick and cb.low < ca.low
        marks_l = [Mark(ca.low, "pavio", 2), Mark(ca.body_bottom, "fracionamento", 2)]
        if b.has_lower_wick and cb.low != ca.low:
            marks_l.append(Mark(cb.low, "pavio", 2))
        name = "futuro_baixa" if futuro else "dupla_posicao"
        return [Structure(name, b.index, a.index, 0, tuple(marks_l), 108 if futuro else 109, "inferior")]
    return []


def nova_alta_baixa(info: CandleInfo, prev_candles: Sequence[Candle], cfg: LdpConfig) -> list[Structure]:
    """Nova alta/baixa: o corpo rompe a zona anterior e a vela deixa um pavio novo (pág. 96-104).

    Acontece após um rompimento das máximas/mínimas recentes ou após uma reversão (pág. 100).
    Marca o pavio e o fechamento (pág. 102). É confluência, não gatilho (pág. 104).
    """
    if not prev_candles or info.direction == 0:
        return []
    c = info.candle
    prev = prev_candles[-1]
    window = prev_candles[-cfg.breakout_window :]
    if info.direction > 0 and info.has_upper_wick:
        rompimento = c.close > max(x.high for x in window)
        reversao = prev.close < prev.open and c.close > prev.high
        if rompimento or reversao:
            marks = (Mark(c.high, "pavio", 2), Mark(c.close, "fechamento", 2))
            return [Structure("nova_alta", info.index, info.index, 1, marks, 102, "rompimento" if rompimento else "reversao")]
    if info.direction < 0 and info.has_lower_wick:
        rompimento = c.close < min(x.low for x in window)
        reversao = prev.close > prev.open and c.close < prev.low
        if rompimento or reversao:
            marks = (Mark(c.low, "pavio", 2), Mark(c.close, "fechamento", 2))
            return [Structure("nova_baixa", info.index, info.index, -1, marks, 102, "rompimento" if rompimento else "reversao")]
    return []


def nova_posicao_marks(info: CandleInfo, direction: int) -> tuple[Mark, ...]:
    """Marcação da nova posição: a projeção (pavio do lado oposto ao movimento) ou, se ela nasceu
    sem pavio (comando único), a abertura, formando divisão de taxa (pág. 129-130, 138 j)."""
    c = info.candle
    if direction > 0:
        return (Mark(c.low, "projecao", 2),) if info.has_lower_wick else (Mark(c.open, "abertura", 3),)
    return (Mark(c.high, "projecao", 2),) if info.has_upper_wick else (Mark(c.open, "abertura", 3),)
