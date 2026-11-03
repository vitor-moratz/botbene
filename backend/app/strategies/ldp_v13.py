"""Port fiel do script "Logica do Preco - CALL PUT com Linhas v1.3" (scripts_iq/).

Mesma lógica do Quadcode Script, vela a vela:
- Comando de alta: vela verde sem pavio na abertura (tolerância `pavio_percentual`) que
  vem depois de uma vela vermelha ou fecha acima da máxima das últimas `janela_ruptura` velas.
- Linha verde = 50% do corpo do último comando de alta FECHADO; vermelha = idem de baixa.
- Setups avaliados na vela fechada k contra a linha que existia ANTES dela:
  reteste, reversão (trava) e rompimento. CALL e PUT ao mesmo tempo se anulam.

Este port serve para comparação no dashboard. A estratégia principal é o motor da apostila.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.market.candle import Candle
from app.strategies.base import Direction, Signal, Strategy


@dataclass
class LdpV13Result:
    signals: list[Signal | None]
    buy_line: list[float | None]  # linha verde vista na vela k (antes de ela fechar)
    sell_line: list[float | None]  # linha vermelha vista na vela k
    cmd_up: list[bool]  # vela k foi comando de alta
    cmd_dn: list[bool]

    def lines_after_close(self, k: int, candles: Sequence[Candle]) -> tuple[float | None, float | None]:
        """Linhas que valem DEPOIS que a vela k fecha (se ela mesma for comando, a linha já muda)."""
        buy = candles[k].mid if self.cmd_up[k] else self.buy_line[k]
        sell = candles[k].mid if self.cmd_dn[k] else self.sell_line[k]
        return buy, sell


class LdpV13(Strategy):
    name = "ldp_v13"

    def __init__(self, pavio_percentual: float = 2.0, janela_ruptura: int = 3, trava_percentual: float = 12.0) -> None:
        self.pavio_percentual = pavio_percentual
        self.janela_ruptura = janela_ruptura
        self.trava_percentual = trava_percentual

    def scan(self, candles: Sequence[Candle]) -> list[Signal | None]:
        return self.analyze(candles).signals

    def analyze(self, candles: Sequence[Candle]) -> LdpV13Result:
        n = len(candles)
        cmd_up = [False] * n
        cmd_dn = [False] * n
        janela = self.janela_ruptura
        for j in range(janela, n):
            c, p = candles[j], candles[j - 1]
            amp = c.high - c.low
            if amp <= 0:
                continue
            tol = amp * self.pavio_percentual / 100
            window = candles[j - janela : j]
            hi_ant = max(x.high for x in window)
            lo_ant = min(x.low for x in window)
            verde, vermelho = c.close > c.open, c.close < c.open
            careca_inicio = (verde and c.open - c.low <= tol) or (vermelho and c.high - c.open <= tol)
            cmd_up[j] = verde and careca_inicio and (p.close < p.open or c.close > hi_ant)
            cmd_dn[j] = vermelho and careca_inicio and (p.close > p.open or c.close < lo_ant)

        # Linha na vela k = 50% do último comando em j <= k-1 (value_when sobre comando[1]).
        buy_line: list[float | None] = [None] * n
        sell_line: list[float | None] = [None] * n
        last_buy: float | None = None
        last_sell: float | None = None
        for k in range(n):
            if k >= 1:
                if cmd_up[k - 1]:
                    last_buy = candles[k - 1].mid
                if cmd_dn[k - 1]:
                    last_sell = candles[k - 1].mid
            buy_line[k], sell_line[k] = last_buy, last_sell

        signals: list[Signal | None] = [None] * n
        for k in range(n):
            c = candles[k]
            sup, res = buy_line[k], sell_line[k]
            ppc = candles[k - 1].close if k >= 1 else None
            po, pc, ph, pl = c.open, c.close, c.high, c.low
            tol_trava = (ph - pl) * self.trava_percentual / 100
            calls: list[str] = []
            puts: list[str] = []
            if sup is not None:
                if pc > po and pl <= sup and pc > sup:
                    calls.append("reteste")
                if pc < po and pl <= sup and pc >= sup and pc - sup <= tol_trava:
                    calls.append("reversao")
                if pc < po and pc < sup and ppc is not None and ppc >= sup:
                    puts.append("rompimento")
            if res is not None:
                if pc < po and ph >= res and pc < res:
                    puts.append("reteste")
                if pc > po and ph >= res and pc <= res and res - pc <= tol_trava:
                    puts.append("reversao")
                if pc > po and pc > res and ppc is not None and ppc <= res:
                    calls.append("rompimento")
            details = {"linha_verde": sup, "linha_vermelha": res}
            if calls and not puts:
                signals[k] = Signal(self.name, k, c.ts, Direction.CALL, "+".join(calls), details)
            elif puts and not calls:
                signals[k] = Signal(self.name, k, c.ts, Direction.PUT, "+".join(puts), details)
        return LdpV13Result(signals, buy_line, sell_line, cmd_up, cmd_dn)
