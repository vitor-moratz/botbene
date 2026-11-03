"""Gestão de risco da sessão: valor da entrada, stop win, stop loss, máximo de entradas, pausa depois
de perdas seguidas e martingale "com análise". Toda ordem passa por aqui antes de ir para a corretora.

Martingale com análise: depois de uma perda, o gale NÃO entra às cegas na vela seguinte; ele vale para
a próxima entrada válida da estratégia (que ainda passa pela aprovação). O valor é calculado para
recuperar a perda do ciclo e ainda ganhar o lucro de uma entrada normal. Um ciclo só começa se o
pior caso dele inteiro couber no stop loss, e com martingale só uma ordem fica aberta por vez.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from app.paper import LOSS, WIN

MAX_GALE_LEVELS = 2


@dataclass(frozen=True)
class RiskConfig:
    stake: float = 2.0  # valor de cada entrada (moeda da conta)
    stop_win: float | None = 20.0  # para a sessão ao ganhar isto
    stop_loss: float | None = 20.0  # para a sessão ao perder isto
    max_trades: int | None = 30
    max_consecutive_losses: int | None = 4
    martingale: bool = False
    gale_levels: int = 1  # quantos gales no máximo por ciclo (1 ou 2)

    def to_dict(self) -> dict:
        return asdict(self)


def gale_stake(base: float, cycle_loss: float, payout: float) -> float:
    """Valor que, se ganhar, cobre a perda do ciclo e ainda rende o lucro de uma entrada normal."""
    return math.ceil((cycle_loss + base * payout) / payout * 100) / 100


class RiskManager:
    def __init__(self, cfg: RiskConfig | None = None) -> None:
        self.cfg = cfg or RiskConfig()
        self.reset()

    def reset(self) -> None:
        self.pnl = 0.0
        self.trades = 0
        self.wins = 0
        self.losses = 0
        self.consecutive_losses = 0
        self.open_orders = 0
        self.open_exposure = 0.0  # soma dos valores das ordens abertas
        self.gale_level = 0  # 0 = entrada normal; 1..N = gale do ciclo atual
        self.cycle_loss = 0.0

    # ------------------------------------------------------------------ valor da próxima entrada

    def next_stake(self, payout: float) -> float:
        if not self.cfg.martingale or self.gale_level == 0:
            return self.cfg.stake
        return gale_stake(self.cfg.stake, self.cycle_loss, payout)

    def cycle_worst_case(self, payout: float) -> float:
        """Perda total se o ciclo inteiro (entrada + todos os gales) der errado, a partir de agora."""
        loss, stake = self.cycle_loss, self.next_stake(payout)
        total = 0.0
        levels_left = (min(self.cfg.gale_levels, MAX_GALE_LEVELS) - self.gale_level) if self.cfg.martingale else 0
        for _ in range(levels_left + 1):
            total += stake
            loss += stake
            stake = gale_stake(self.cfg.stake, loss, payout)
        return round(total, 2)

    # ------------------------------------------------------------------ pode operar?

    def check(self, payout: float = 0.85) -> tuple[bool, str]:
        """Pode abrir mais uma ordem? Inclui as que ainda estão abertas no pior caso (todas perdem)."""
        c = self.cfg
        worst = self.pnl - self.open_exposure
        if c.stop_win is not None and self.pnl >= c.stop_win:
            return False, f"stop win atingido (+{self.pnl:.2f})"
        if c.martingale and self.open_orders:
            return False, "martingale: esperando o resultado da ordem anterior"
        needed = self.cycle_worst_case(payout) if c.martingale else self.next_stake(payout)
        if c.stop_loss is not None and worst - needed < -c.stop_loss - 1e-9:
            what = "o ciclo de martingale inteiro" if c.martingale and self.gale_level == 0 else "mais uma entrada"
            return False, f"stop loss: {what} poderia passar de {c.stop_loss:.2f} de perda"
        if c.max_trades is not None and self.trades + self.open_orders >= c.max_trades:
            return False, f"limite de {c.max_trades} entradas na sessão"
        if c.max_consecutive_losses is not None and self.consecutive_losses >= c.max_consecutive_losses:
            return False, f"{self.consecutive_losses} perdas seguidas: pausa para reavaliar"
        return True, "ok"

    # ------------------------------------------------------------------ ciclo de uma ordem

    def opened(self, amount: float | None = None) -> None:
        self.open_orders += 1
        self.open_exposure = round(self.open_exposure + (self.cfg.stake if amount is None else amount), 2)

    def cancel(self, amount: float | None = None) -> None:
        """A ordem reservada não chegou a ser aceita pela corretora."""
        self.open_orders = max(0, self.open_orders - 1)
        self.open_exposure = max(0.0, round(self.open_exposure - (self.cfg.stake if amount is None else amount), 2))

    def closed(self, result: str, profit: float, amount: float | None = None) -> None:
        self.open_orders = max(0, self.open_orders - 1)
        self.open_exposure = max(0.0, round(self.open_exposure - (self.cfg.stake if amount is None else amount), 2))
        self.trades += 1
        self.pnl = round(self.pnl + profit, 2)
        if result == WIN:
            self.wins += 1
            self.consecutive_losses = 0
            self.gale_level, self.cycle_loss = 0, 0.0
        elif result == LOSS:
            self.losses += 1
            self.consecutive_losses += 1
            if self.cfg.martingale and self.gale_level < min(self.cfg.gale_levels, MAX_GALE_LEVELS):
                self.gale_level += 1
                self.cycle_loss = round(self.cycle_loss - profit, 2)
            else:  # ciclo perdido (ou sem martingale): volta à entrada normal
                self.gale_level, self.cycle_loss = 0, 0.0

    def snapshot(self, payout: float = 0.85) -> dict:
        ok, why = self.check(payout)
        return {"config": self.cfg.to_dict(), "pnl": self.pnl, "trades": self.trades, "wins": self.wins,
                "losses": self.losses, "consecutive_losses": self.consecutive_losses,
                "open_orders": self.open_orders, "can_trade": ok, "reason": why,
                "gale_level": self.gale_level, "next_stake": self.next_stake(payout)}
