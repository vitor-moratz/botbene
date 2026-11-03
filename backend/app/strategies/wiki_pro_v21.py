"""Port fiel do script "IQ WIKI PRO V2.1 - Logica do Preco" (scripts_iq/).

Na plataforma, o sinal da barra atual usa só valores [1] e [2] (velas fechadas) e é
desenhado com deslocamento -1. Aqui isso vira: sinal no fechamento da vela k, usando k e k-1.

Observação (ver docs/estrategia.md): dos 3 pontos exigidos, 2 já são condições obrigatórias
(ação do preço + força/comando), então basta 1 indicador concordar. A "vela de força" deste
script é "corpo grande", não a da apostila. Serve como filtro de tendência, não como decisor.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.indicators.core import dmi_adx, ema, highest, lowest, rma, rsi, true_range
from app.market.candle import Candle
from app.strategies.base import Direction, Signal, Strategy


class WikiProV21(Strategy):
    name = "wiki_pro_v21"

    def __init__(
        self,
        ema_fast_period: int = 9,
        ema_slow_period: int = 21,
        ema_anchor_period: int = 50,
        rsi_period: int = 14,
        adx_period: int = 14,
        adx_min: float = 18.0,
        atr_period: int = 14,
        atr_base_period: int = 20,
        breakout_period: int = 5,
        min_body_ratio: float = 0.55,
        max_extension_atr: float = 1.25,
    ) -> None:
        self.ema_fast_period = ema_fast_period
        self.ema_slow_period = ema_slow_period
        self.ema_anchor_period = ema_anchor_period
        self.rsi_period = rsi_period
        self.adx_period = adx_period
        self.adx_min = adx_min
        self.atr_period = atr_period
        self.atr_base_period = atr_base_period
        self.breakout_period = breakout_period
        self.min_body_ratio = min_body_ratio
        self.max_extension_atr = max_extension_atr

    def scan(self, candles: Sequence[Candle]) -> list[Signal | None]:
        n = len(candles)
        o = [c.open for c in candles]
        h = [c.high for c in candles]
        lo = [c.low for c in candles]
        cl = [c.close for c in candles]

        ema_fast = ema(cl, self.ema_fast_period)
        ema_slow = ema(cl, self.ema_slow_period)
        ema_anchor = ema(cl, self.ema_anchor_period)
        rsi_v = rsi(cl, self.rsi_period)
        plus_di, minus_di, adx = dmi_adx(h, lo, cl, self.adx_period)
        atr = rma(true_range(h, lo, cl), self.atr_period)
        atr_base = ema(atr, self.atr_base_period)
        hh = highest(h, self.breakout_period)
        ll = lowest(lo, self.breakout_period)

        signals: list[Signal | None] = [None] * n
        for k in range(1, n):
            needed = (
                ema_fast[k], ema_slow[k], ema_slow[k - 1], ema_anchor[k], rsi_v[k],
                adx[k], plus_di[k], minus_di[k], atr[k], atr_base[k], hh[k - 1], ll[k - 1],
            )
            if any(v is None for v in needed):
                continue
            ef, es, es_prev, ea = ema_fast[k], ema_slow[k], ema_slow[k - 1], ema_anchor[k]
            r, a, pdi, mdi = rsi_v[k], adx[k], plus_di[k], minus_di[k]
            atr_k, atr_b = atr[k], atr_base[k]

            c_open, c_high, c_low, c_close = o[k], h[k], lo[k], cl[k]
            c_range = max(c_high - c_low, 1e-7)
            c_body = abs(c_close - c_open)
            body_ratio = c_body / c_range
            upper_wick = c_high - max(c_open, c_close)
            lower_wick = min(c_open, c_close) - c_low

            trend_up = ef > es and es > ea and es > es_prev
            trend_down = ef < es and es < ea and es < es_prev
            momentum_up = 52 <= r <= 68
            momentum_down = 32 <= r <= 48
            strength_up = a >= self.adx_min and pdi > mdi
            strength_down = a >= self.adx_min and mdi > pdi

            force_up = c_close > c_open and body_ratio >= self.min_body_ratio and upper_wick <= c_body * 0.45
            force_down = c_close < c_open and body_ratio >= self.min_body_ratio and lower_wick <= c_body * 0.45
            command_up = c_close > c_open and lower_wick <= c_range * 0.08
            command_down = c_close < c_open and upper_wick <= c_range * 0.08

            break_up = c_close > hh[k - 1] and c_close > c_open
            break_down = c_close < ll[k - 1] and c_close < c_open
            pullback_up = c_low <= ef and c_close > ef and c_close > c_open
            pullback_down = c_high >= ef and c_close < ef and c_close < c_open

            po, pcl, ph, pl = o[k - 1], cl[k - 1], h[k - 1], lo[k - 1]
            prev_upper_wick = ph - max(po, pcl)
            prev_lower_wick = min(po, pcl) - pl
            double_up = c_close > max(po, pcl) and c_close <= ph and prev_upper_wick > 0
            double_down = c_close < min(po, pcl) and c_close >= pl and prev_lower_wick > 0

            pa_up = break_up or pullback_up or (double_up and force_up)
            pa_down = break_down or pullback_down or (double_down and force_down)

            atr_active = atr_k >= atr_b * 0.85
            not_ext_up = (c_close - ef) <= atr_k * self.max_extension_atr
            not_ext_down = (ef - c_close) <= atr_k * self.max_extension_atr

            score_up = sum((trend_up, momentum_up, strength_up, pa_up, force_up or command_up))
            score_down = sum((trend_down, momentum_down, strength_down, pa_down, force_down or command_down))

            call = pa_up and (force_up or command_up) and atr_active and not_ext_up and score_up >= 3
            put = pa_down and (force_down or command_down) and atr_active and not_ext_down and score_down >= 3
            if call:
                details = {"score": score_up, "tendencia": trend_up, "momentum": momentum_up, "forca_adx": strength_up}
                signals[k] = Signal(self.name, k, candles[k].ts, Direction.CALL, "wiki_score", details)
            elif put:
                details = {"score": score_down, "tendencia": trend_down, "momentum": momentum_down, "forca_adx": strength_down}
                signals[k] = Signal(self.name, k, candles[k].ts, Direction.PUT, "wiki_score", details)
        return signals
