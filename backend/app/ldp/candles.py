"""Classificação de cada vela segundo a apostila (Parte I).

Pavio de ABERTURA = o lado onde a vela nasce: embaixo na vela de alta (verde),
em cima na vela de baixa (vermelha). Pavio de FECHAMENTO = o lado oposto.

| Abertura   | Fechamento | Classe                                                   |
|------------|------------|----------------------------------------------------------|
| sem pavio  | sem pavio  | C1: comando nível 1 / controle de região (pág. 17-19, 24) |
| sem pavio  | com pavio  | C2: comando único, nível 2 (pág. 6-9, 24)                |
| com pavio  | sem pavio  | C3: expirado / fim de taxa, nível 3 (pág. 21-24)         |
| com pavio  | com pavio  | vela de força (pág. 11-16) ou indecisão, pelo corpo      |

Com essa divisão, comando e vela de força nunca se confundem (pág. 11).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from app.ldp.config import LdpConfig
from app.market.candle import Candle


class CandleClass(str, Enum):
    C1 = "comando_n1"
    C2 = "comando_unico"
    C3 = "expirado"
    FORCA = "vela_de_forca"
    INDECISAO = "indecisao"
    DOJI = "doji"


@dataclass(frozen=True, slots=True)
class CandleInfo:
    index: int
    candle: Candle
    direction: int  # +1 alta, -1 baixa, 0 sem cor
    cls: CandleClass
    open_wick: float
    close_wick: float
    has_open_wick: bool
    has_close_wick: bool
    has_upper_wick: bool
    has_lower_wick: bool
    gap: float
    has_gap: bool
    # Para comandos (C1/C2): em que situação nasceu: "reversao", "rompimento" ou "fracionamento" (pág. 6-7).
    cmd_context: str | None

    @property
    def comando_level(self) -> int | None:
        """Nível do comando (pág. 24): 1 = careca dos dois lados, 2 = comando único, 3 = expirado."""
        return {CandleClass.C1: 1, CandleClass.C2: 2, CandleClass.C3: 3}.get(self.cls)

    @property
    def open_wick_tip(self) -> float:
        """Ponta do pavio de abertura (mínima na alta, máxima na baixa)."""
        return self.candle.low if self.direction > 0 else self.candle.high

    @property
    def close_wick_tip(self) -> float:
        """Ponta do pavio de fechamento (máxima na alta, mínima na baixa)."""
        return self.candle.high if self.direction > 0 else self.candle.low


def classify(candle: Candle, index: int, prev_candles: Sequence[Candle], cfg: LdpConfig) -> CandleInfo:
    """Classifica `candle`. `prev_candles` são as velas anteriores (a última é a imediatamente anterior)."""
    prev = prev_candles[-1] if prev_candles else None
    rng = candle.range
    body = candle.body
    tol = rng * cfg.wick_tol_pct

    gap = abs(candle.open - prev.close) if prev else 0.0
    has_gap = prev is not None and gap > max(prev.range, 0.0) * cfg.gap_tol_pct and gap > 0

    has_upper = candle.upper_wick > tol
    has_lower = candle.lower_wick > tol

    if rng <= 0 or body <= rng * cfg.doji_body_pct:
        return CandleInfo(
            index=index,
            candle=candle,
            direction=0,
            cls=CandleClass.DOJI,
            open_wick=0.0,
            close_wick=0.0,
            has_open_wick=has_upper or has_lower,
            has_close_wick=has_upper or has_lower,
            has_upper_wick=has_upper,
            has_lower_wick=has_lower,
            gap=gap,
            has_gap=has_gap,
            cmd_context=None,
        )

    direction = 1 if candle.close > candle.open else -1
    if direction > 0:
        open_wick, close_wick = candle.lower_wick, candle.upper_wick
    else:
        open_wick, close_wick = candle.upper_wick, candle.lower_wick
    has_open, has_close = open_wick > tol, close_wick > tol

    if not has_open and not has_close:
        cls = CandleClass.C1
    elif not has_open:
        cls = CandleClass.C2
    elif not has_close:
        cls = CandleClass.C3
    else:
        # Vela de força também é a de corpo enxuto que rompe máxima/mínima anterior (pág. 12).
        breaks_prev = prev is not None and (
            (direction > 0 and candle.close > prev.high) or (direction < 0 and candle.close < prev.low)
        )
        cls = CandleClass.FORCA if body >= rng * cfg.forca_min_body_pct or breaks_prev else CandleClass.INDECISAO

    cmd_context = None
    if cls in (CandleClass.C1, CandleClass.C2):
        window = prev_candles[-cfg.breakout_window :]
        if prev is not None and ((direction > 0 and prev.close < prev.open) or (direction < 0 and prev.close > prev.open)):
            cmd_context = "reversao"
        elif window and (
            (direction > 0 and candle.close > max(c.high for c in window))
            or (direction < 0 and candle.close < min(c.low for c in window))
        ):
            cmd_context = "rompimento"
        else:
            cmd_context = "fracionamento"

    return CandleInfo(
        index=index,
        candle=candle,
        direction=direction,
        cls=cls,
        open_wick=open_wick,
        close_wick=close_wick,
        has_open_wick=has_open,
        has_close_wick=has_close,
        has_upper_wick=has_upper,
        has_lower_wick=has_lower,
        gap=gap,
        has_gap=has_gap,
        cmd_context=cmd_context,
    )
