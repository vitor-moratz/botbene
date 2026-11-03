"""Corretora falsa para testar o bot sem a IQ Option: entrega o histórico e depois uma vela nova por consulta."""

from __future__ import annotations

from app.broker.base import AccountType, Broker, BrokerError, OrderResult, OrderTicket
from app.market.candle import Candle


class FakeBroker(Broker):
    def __init__(self, history: list[Candle], live: list[Candle], payout: float = 0.8,
                 sub: list[Candle] | None = None, archive: list[Candle] | None = None) -> None:
        self.history = history
        self.live = list(live)
        self.account = AccountType.PRACTICE
        self._payout = payout
        self._last_ts = history[-1].ts if history else 0
        # O que get_candles devolve por timeframe. `archive` = histórico completo (para o resolvedor).
        self.series: dict[int, list[Candle]] = {60: archive if archive is not None else history}
        if sub:
            self.series[5] = sub
        self.get_candles_calls = 0
        self.tickets: list[OrderTicket] = []
        self.results: dict[int, OrderResult] = {}  # resultado por ordem (padrão: win com 80%)
        self.refuse_orders: str | None = None

    def connect(self) -> None: ...

    def buy(self, asset, direction, amount, minutes=1):
        if self.refuse_orders:
            raise BrokerError(self.refuse_orders)
        now = self.server_time()
        t = OrderTicket(len(self.tickets) + 1, asset, direction, amount, self.account.value, now, int(now))
        self.tickets.append(t)
        return t

    def order_result(self, ticket):
        return self.results.get(ticket.order_id, OrderResult("win", round(ticket.amount * self._payout, 2)))

    def is_connected(self) -> bool:
        return True

    def set_account(self, account: AccountType) -> None:
        self.account = account

    def balance(self) -> float:
        return 10_000.0

    def server_time(self) -> float:
        return self._last_ts + 1  # nunca força o fechamento por tempo

    def get_candles(self, asset, timeframe, count, end_ts=None):
        self.get_candles_calls += 1
        data = self.series.get(timeframe, [])
        if end_ts is not None:
            data = [c for c in data if c.ts + timeframe <= end_ts]
        return data[-count:]

    def start_stream(self, asset, timeframe, buffer=10) -> None: ...

    def stop_stream(self, asset, timeframe) -> None: ...

    def stream_candles(self, asset, timeframe):
        if not self.live:
            return []
        candle = self.live.pop(0)
        self._last_ts = candle.ts
        return [candle]

    def open_assets(self, option_type="turbo"):
        return {"EURUSD": True}

    def payouts(self, option_type="turbo"):
        return {"EURUSD": self._payout}
