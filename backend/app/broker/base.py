"""Interface da corretora. O resto do bot só conhece esta interface, então trocar a
biblioteca da IQ Option (que é não oficial e pode quebrar) mexe em um arquivo só."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from app.market.candle import Candle


class AccountType(str, Enum):
    PRACTICE = "PRACTICE"
    REAL = "REAL"


class BrokerError(RuntimeError):
    pass


@dataclass(frozen=True)
class OrderTicket:
    order_id: int
    asset: str
    direction: str  # "call" | "put"
    amount: float
    account: str
    opened_at: float  # horário do servidor
    expires_at: int  # fim da vela de 1 min em que a ordem entrou


@dataclass(frozen=True)
class OrderResult:
    result: str  # "win" | "loss" | "empate" (mesmos nomes do modo paper)
    profit: float  # em dinheiro: ganho líquido, ou -valor na perda


def expiry_for(server_ts: float, minutes: int = 1) -> int:
    """Vencimento que a IQ dá para uma binária de 1 min: fim do minuto atual se faltarem mais de
    30 s, senão o fim do minuto seguinte."""
    end = (int(server_ts) // 60 + 1) * 60
    if end - server_ts <= 30:
        end += 60
    return end + 60 * (minutes - 1)


class Broker(ABC):
    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def is_connected(self) -> bool: ...

    @abstractmethod
    def set_account(self, account: AccountType) -> None: ...

    @abstractmethod
    def balance(self) -> float: ...

    @abstractmethod
    def server_time(self) -> float:
        """Horário do servidor da corretora, em segundos (epoch)."""

    @abstractmethod
    def get_candles(self, asset: str, timeframe: int, count: int, end_ts: float | None = None) -> list[Candle]:
        """Histórico de velas FECHADAS, da mais antiga para a mais nova."""

    @abstractmethod
    def start_stream(self, asset: str, timeframe: int, buffer: int = 10) -> None: ...

    @abstractmethod
    def stop_stream(self, asset: str, timeframe: int) -> None: ...

    @abstractmethod
    def stream_candles(self, asset: str, timeframe: int) -> list[Candle]:
        """Últimas velas do stream (a última pode estar em formação)."""

    @abstractmethod
    def open_assets(self, option_type: str = "turbo") -> dict[str, bool]: ...

    @abstractmethod
    def payouts(self, option_type: str = "turbo") -> dict[str, float]:
        """Payout por ativo em fração (0.85 = 85%)."""

    def disconnect(self) -> None:
        """Fecha a conexão (ao trocar de login). Padrão: nada a fazer."""

    def currency(self) -> str:
        """Moeda da conta (a demo da IQ costuma ser em dólar)."""
        return "USD"

    def tradable(self, asset: str) -> tuple[bool, str]:
        """Dá para comprar binária de 1 min neste ativo agora? Nunca espera pela corretora."""
        return True, "ok"

    def payout_now(self, asset: str) -> float | None:
        """Payout atual da binária de 1 min, do que já está em memória (nunca espera). None = não sabe."""
        return None

    def buy(self, asset: str, direction: str, amount: float, minutes: int = 1) -> OrderTicket:
        """Envia uma ordem binária (turbo). Levanta BrokerError se a corretora recusar."""
        raise BrokerError("Esta corretora não envia ordens")

    def order_result(self, ticket: OrderTicket) -> OrderResult | None:
        """Resultado da ordem, ou None se ela ainda não fechou."""
        raise BrokerError("Esta corretora não envia ordens")
