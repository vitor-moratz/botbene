"""Gestão de risco da sessão: valor da entrada, stop win, stop loss, máximo de entradas, pausa depois
de perdas seguidas, martingale "com análise" e stop de ciclos perdidos. Toda ordem passa por aqui antes de ir
para a corretora.

Martingale com análise: depois de uma perda, o gale NÃO entra às cegas na vela seguinte; ele vale para
a próxima entrada válida da estratégia (que ainda passa pela aprovação). O valor é calculado para
recuperar a perda do ciclo e ainda ganhar o lucro de uma entrada normal. Um ciclo só começa se o pior caso
dele inteiro, somado ao que ainda falta nos outros ciclos em andamento, couber no stop loss, e só uma ordem
de cada ciclo fica aberta por vez. Se a próxima entrada cai logo na vela seguinte, o bot espera o resultado da
ordem anterior (chega ~1 s depois da vela abrir) dentro da janela de entrada, em vez de bloquear
(service/bot.py, WAIT_GALE).

Gale por estratégia: só as estratégias marcadas (`gale_strategies`) usam o gale, e cada uma tem o seu próprio
ciclo. Até 09/11/2026 elas dividiam um ciclo só, com uma ordem aberta por vez entre todas: a Bollinger, que
entra no início de quase toda vela, ficava com a vaga e a retração no comando (que dispara segundos depois)
quase nunca entrava. As não marcadas entram sempre com o valor normal e não mexem em ciclo nenhum. Stops,
máximo de entradas e perdas seguidas continuam valendo para todas juntas.

Stop de ciclo (`max_lost_cycles`): para de abrir entradas depois de N ciclos de gale perdidos inteiros na sessão
(perdeu a entrada e todos os gales), somando todas as estratégias.

Stop loss que acompanha o lucro (`stop_loss_trail`, 10/11/2026): o limite passa a contar do melhor resultado da sessão
(fechado), e não do Iniciar. Com stop loss de 50, a sessão que chegou a +80 para de abrir ordens se puder cair abaixo de
+30. Antes de ter lucro vale igual ao normal (até -50 desde o Iniciar): o piso só sobe, nunca desce. Quando o piso
sobe, o resultado está no melhor ponto, então sobra o stop loss inteiro para os gales dos ciclos abertos.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import asdict, dataclass, field

from app.paper import LOSS, WIN

MAX_GALE_LEVELS = 2


@dataclass(frozen=True)
class RiskConfig:
    stake: float = 2.0  # valor de cada entrada (moeda da conta)
    stop_win: float | None = 20.0  # para a sessão ao ganhar isto
    stop_loss: float | None = 20.0  # para a sessão ao perder isto
    stop_loss_trail: bool = False  # o stop loss conta do melhor resultado da sessão (protege o lucro), não do Iniciar
    max_trades: int | None = 30
    max_consecutive_losses: int | None = 4
    martingale: bool = False
    gale_levels: int = 1  # quantos gales no máximo por ciclo (1 ou 2)
    # Estratégias que usam o gale. None = todas (como era antes da escolha por estratégia).
    gale_strategies: tuple[str, ...] | None = None
    max_lost_cycles: int | None = None  # stop de ciclo: para depois de N ciclos de gale perdidos na sessão

    def to_dict(self) -> dict:
        d = asdict(self)
        if self.gale_strategies is not None:
            d["gale_strategies"] = list(self.gale_strategies)
        return d


def gale_stake(base: float, cycle_loss: float, payout: float) -> float:
    """Valor que, se ganhar, cobre a perda do ciclo e ainda rende o lucro de uma entrada normal."""
    return math.ceil((cycle_loss + base * payout) / payout * 100) / 100


@dataclass
class GaleCycle:
    level: int = 0  # 0 = entrada normal; 1..N = gale
    loss: float = 0.0  # perdido até agora no ciclo
    stakes: list[float] = field(default_factory=list)  # valores das ordens já perdidas (para o painel)


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
        self.open_by_strategy: Counter = Counter()  # ordens abertas por estratégia (None = sem nome)
        self.open_amount: Counter = Counter()  # valor aberto por estratégia
        self.cycles: dict[str | None, GaleCycle] = {}  # ciclo de gale em andamento de cada estratégia
        self.lost_cycles = 0  # ciclos de gale perdidos inteiros na sessão
        self.peak_pnl = 0.0  # melhor resultado fechado da sessão (o stop loss que acompanha o lucro conta daqui)

    # ------------------------------------------------------------------ quem usa o gale

    def uses_gale(self, strategy: str | None = None) -> bool:
        c = self.cfg
        if not c.martingale:
            return False
        return c.gale_strategies is None or (strategy is not None and strategy in c.gale_strategies)

    @property
    def max_level(self) -> int:
        return min(self.cfg.gale_levels, MAX_GALE_LEVELS) if self.cfg.martingale else 0

    def cycle(self, strategy: str | None = None) -> GaleCycle:
        """Ciclo desta estratégia (vazio se não há nenhum em andamento)."""
        return self.cycles.get(strategy) or GaleCycle()

    def gale_open(self, strategy: str | None) -> bool:
        """Esta estratégia usa o gale e tem ordem aberta (o próximo valor dela depende desse resultado)?"""
        return self.uses_gale(strategy) and self.open_by_strategy[strategy] > 0

    @property
    def open_gale_orders(self) -> int:
        """Ordens abertas de estratégias que usam o gale (conta com a configuração atual)."""
        return sum(n for s, n in self.open_by_strategy.items() if n > 0 and self.uses_gale(s))

    def _active(self) -> list[str | None]:
        """Estratégias do gale com ciclo em andamento (já perdeu no ciclo ou tem ordem aberta), na ordem da lista."""
        names = set(self.cycles) | {s for s, n in self.open_by_strategy.items() if n > 0}
        names = {s for s in names if self.uses_gale(s) and (self.cycle(s).level > 0 or self.open_by_strategy[s] > 0)}
        order = list(self.cfg.gale_strategies or ())
        return sorted(names, key=lambda s: (order.index(s) if s in order else len(order), str(s)))

    def _main(self) -> str | None:
        """O ciclo mais adiantado (para quem olha um ciclo só: o painel antigo e o resumo)."""
        active = self._active()
        if not active:
            return None
        return max(active, key=lambda s: (self.cycle(s).level, self.open_by_strategy[s] > 0))

    # Leitura de um ciclo só (o mais adiantado), como era quando todas dividiam o mesmo ciclo.
    @property
    def gale_level(self) -> int:
        return self.cycle(self._main()).level

    @property
    def cycle_loss(self) -> float:
        return self.cycle(self._main()).loss

    @property
    def cycle_stakes(self) -> list[float]:
        return list(self.cycle(self._main()).stakes)

    # ------------------------------------------------------------------ valor da próxima entrada

    def gale_next_stake(self, payout: float, strategy: str | None = None) -> float:
        """Valor da próxima entrada desta estratégia, se ela usa o gale."""
        cyc = self.cycle(strategy)
        if cyc.level == 0:
            return self.cfg.stake
        return gale_stake(self.cfg.stake, cyc.loss, payout)

    def next_stake(self, payout: float, strategy: str | None = None) -> float:
        return self.gale_next_stake(payout, strategy) if self.uses_gale(strategy) else self.cfg.stake

    def _stakes_from(self, level: int, loss: float, payout: float) -> float:
        """Soma das entradas do nível `level` até o último gale, se todas perderem, com `loss` já perdido no ciclo."""
        stake = self.cfg.stake if level == 0 else gale_stake(self.cfg.stake, loss, payout)
        total = 0.0
        for _ in range(max(0, self.max_level - level) + 1):
            total += stake
            loss += stake
            stake = gale_stake(self.cfg.stake, loss, payout)
        return round(total, 2)

    def cycle_worst_case(self, payout: float, strategy: str | None = None) -> float:
        """Perda total se o ciclo desta estratégia inteiro (entrada + todos os gales) der errado, a partir de agora."""
        cyc = self.cycle(strategy)
        return self._stakes_from(cyc.level, cyc.loss, payout)

    def _still_to_lose(self, payout: float, strategy: str | None) -> float:
        """O que o ciclo desta estratégia ainda pode perder além da ordem já aberta (essa entra em open_exposure)."""
        if not self.uses_gale(strategy):
            return 0.0
        cyc = self.cycle(strategy)
        if self.open_by_strategy[strategy] > 0:
            if cyc.level >= self.max_level:
                return 0.0
            return self._stakes_from(cyc.level + 1, cyc.loss + self.open_amount[strategy], payout)
        return self.cycle_worst_case(payout, strategy) if cyc.level > 0 else 0.0

    def _reserved_by_others(self, payout: float, strategy: str | None) -> float:
        """Gales que ainda podem vir nos ciclos em andamento das outras estratégias."""
        return round(sum(self._still_to_lose(payout, s) for s in self._active() if s != strategy), 2)

    # ------------------------------------------------------------------ pode operar?

    @property
    def stop_floor(self) -> float | None:
        """Resultado da sessão abaixo do qual nenhuma ordem nova sai (None = sem stop loss)."""
        if self.cfg.stop_loss is None:
            return None
        base = self.peak_pnl if self.cfg.stop_loss_trail else 0.0
        return round(base - self.cfg.stop_loss, 2)

    def check(self, payout: float = 0.85, strategy: str | None = None) -> tuple[bool, str]:
        """Pode abrir mais uma ordem desta estratégia? Inclui as que ainda estão abertas no pior caso (todas perdem)
        e os gales que ainda podem vir nos ciclos das outras estratégias."""
        c = self.cfg
        gale = self.uses_gale(strategy)
        worst = self.pnl - self.open_exposure
        if c.stop_win is not None and self.pnl >= c.stop_win:
            return False, f"stop win atingido (+{self.pnl:.2f})"
        if c.max_lost_cycles is not None and self.lost_cycles >= c.max_lost_cycles:
            n = self.lost_cycles
            return False, f"stop de ciclo: {n} ciclo{'s' if n > 1 else ''} de gale perdido{'s' if n > 1 else ''} (máximo {c.max_lost_cycles})"
        if gale and self.open_by_strategy[strategy] > 0:
            return False, "martingale: esperando o resultado da ordem anterior"
        reserved = self._reserved_by_others(payout, strategy)
        needed = (self.cycle_worst_case(payout, strategy) if gale else c.stake) + reserved
        floor = self.stop_floor
        if floor is not None and worst - needed < floor - 1e-9:
            what = "o ciclo de martingale inteiro" if gale and self.cycle(strategy).level == 0 else "mais uma entrada"
            others = " junto com os gales que ainda podem vir em outro ciclo" if reserved else ""
            if c.stop_loss_trail and self.peak_pnl > 0:
                return False, (f"stop loss acompanhando o lucro: {what}{others} poderia deixar a sessão abaixo de "
                               f"{floor:+.2f} (melhor ponto {self.peak_pnl:+.2f} menos {c.stop_loss:.2f})")
            return False, f"stop loss: {what}{others} poderia passar de {c.stop_loss:.2f} de perda"
        if c.max_trades is not None and self.trades + self.open_orders >= c.max_trades:
            return False, f"limite de {c.max_trades} entradas na sessão"
        if c.max_consecutive_losses is not None and self.consecutive_losses >= c.max_consecutive_losses:
            return False, f"{self.consecutive_losses} perdas seguidas: pausa para reavaliar"
        return True, "ok"

    # ------------------------------------------------------------------ ciclo de uma ordem

    def _release(self, amount: float | None, strategy: str | None) -> None:
        value = self.cfg.stake if amount is None else amount
        self.open_orders = max(0, self.open_orders - 1)
        self.open_exposure = max(0.0, round(self.open_exposure - value, 2))
        if self.open_by_strategy[strategy] > 0:
            self.open_by_strategy[strategy] -= 1
            self.open_amount[strategy] = max(0.0, round(self.open_amount[strategy] - value, 2))

    def opened(self, amount: float | None = None, strategy: str | None = None) -> None:
        value = self.cfg.stake if amount is None else amount
        self.open_orders += 1
        self.open_exposure = round(self.open_exposure + value, 2)
        self.open_by_strategy[strategy] += 1
        self.open_amount[strategy] = round(self.open_amount[strategy] + value, 2)

    def cancel(self, amount: float | None = None, strategy: str | None = None) -> None:
        """A ordem reservada não chegou a ser aceita pela corretora."""
        self._release(amount, strategy)

    def closed(self, result: str, profit: float, amount: float | None = None, strategy: str | None = None) -> None:
        self._release(amount, strategy)
        self.trades += 1
        self.pnl = round(self.pnl + profit, 2)
        self.peak_pnl = max(self.peak_pnl, self.pnl)
        if not self.cfg.martingale:
            self.cycles.clear()  # martingale desligado: nenhum ciclo continua
        gale = self.uses_gale(strategy)
        if not gale:
            self.cycles.pop(strategy, None)  # saiu da lista do gale: o ciclo dela acabou
        if result == WIN:
            self.wins += 1
            self.consecutive_losses = 0
            if gale:  # vitória fecha só o ciclo desta estratégia
                self.cycles.pop(strategy, None)
        elif result == LOSS:
            self.losses += 1
            self.consecutive_losses += 1
            if gale:
                cyc = self.cycles.setdefault(strategy, GaleCycle())
                if cyc.level < self.max_level:
                    cyc.level += 1
                    cyc.loss = round(cyc.loss - profit, 2)
                    cyc.stakes.append(round(-profit, 2))
                else:  # perdeu até o último gale: ciclo perdido, volta à entrada normal
                    self.lost_cycles += 1
                    self.cycles.pop(strategy, None)

    def _cycle_view(self, strategy: str | None, payout: float) -> dict:
        cyc = self.cycle(strategy)
        return {"strategy": strategy, "gale_level": cyc.level, "next_stake": self.gale_next_stake(payout, strategy),
                "cycle_loss": cyc.loss, "cycle_stakes": list(cyc.stakes), "gale_open": self.open_by_strategy[strategy] > 0,
                # perda total do ciclo se ele perder até o último gale
                "cycle_worst": round(cyc.loss + self.cycle_worst_case(payout, strategy), 2)}

    def snapshot(self, payout: float = 0.85) -> dict:
        ok, why = self.check(payout)
        on = self.cfg.martingale
        cycles = [self._cycle_view(s, payout) for s in self._active()] if on else []
        main = max(cycles, key=lambda v: (v["gale_level"], v["gale_open"])) if cycles else None
        fresh = {"gale_level": 0, "next_stake": self.cfg.stake, "cycle_loss": 0.0, "cycle_stakes": [], "gale_open": False,
                 "cycle_worst": self._stakes_from(0, 0.0, payout) if on else 0.0}
        top = {k: v for k, v in (main or fresh).items() if k != "strategy"}
        return {"config": self.cfg.to_dict(), "pnl": self.pnl, "trades": self.trades, "wins": self.wins,
                "losses": self.losses, "consecutive_losses": self.consecutive_losses,
                "open_orders": self.open_orders, "can_trade": ok, "reason": why,
                # ciclo mais adiantado (painel antigo); `cycles` traz cada ciclo em andamento, um por estratégia
                **top, "cycles": cycles, "lost_cycles": self.lost_cycles,
                "peak_pnl": self.peak_pnl, "stop_floor": self.stop_floor}
