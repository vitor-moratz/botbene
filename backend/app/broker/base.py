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


class OrderRefused(BrokerError):
    """A ordem com certeza não foi comprada: a corretora respondeu que não aceita, ou o par está fechado para o tipo.
    Num BrokerError comum (ex.: sem resposta a tempo) a ordem pode ter entrado; aqui dá para tentar o outro tipo
    sem risco de entrar duas vezes."""


# Tipos de opção da IQ. Os dois usam o mesmo ativo e o mesmo preço (EURUSD-op, EURUSD-OTC): muda só o produto
# comprado. Binária: payout fixo na hora da compra. Digital: payout que a IQ recalcula o tempo todo.
BINARY, DIGITAL = "binary", "digital"
OPTION_KINDS = (BINARY, DIGITAL)
KIND_LABELS = {BINARY: "binária", DIGITAL: "digital"}
DIGITAL_MINUTES = (1, 5)  # vencimentos da digital que o bot oferece (a IQ também tem 15 min)


@dataclass(frozen=True)
class OrderTicket:
    order_id: int
    asset: str
    direction: str  # "call" | "put"
    amount: float
    account: str
    opened_at: float  # horário do servidor
    expires_at: int  # fim da vela de 1 min em que a ordem entrou
    kind: str = BINARY  # binary | digital


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


def digital_expiry_for(server_ts: float, minutes: int = 1) -> int:
    """Vencimento da digital: o próximo horário múltiplo do prazo (1 min: virada do minuto; 5 min: :00, :05…)
    que esteja a mais de 30 s. Para 1 min, é a mesma regra da binária."""
    if minutes not in DIGITAL_MINUTES:
        raise BrokerError(f"A digital não tem vencimento de {minutes} min (só {', '.join(map(str, DIGITAL_MINUTES))})")
    step = 60 * minutes
    end = (int(server_ts) // step + 1) * step
    if end - server_ts <= 30:
        end += step
    return end


class Broker(ABC):
    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def is_connected(self) -> bool: ...

    @abstractmethod
    def set_account(self, account: AccountType) -> None: ...

    @abstractmethod
    def balance(self) -> float: ...

    def balance_info(self) -> tuple[float, float]:
        """(saldo, bônus) da conta em uso. Na IQ o bônus vem separado e o site mostra os dois somados."""
        return self.balance(), 0.0

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

    def release_stream(self, asset: str, timeframe: int) -> None:
        """Cancela o stream sem esperar a corretora confirmar (ao parar o bot). Padrão: `stop_stream`."""
        self.stop_stream(asset, timeframe)

    def pairs(self) -> list[dict]:
        """Pares para escolher na tela: asset, label, category, payout, open, reason, min, max e expiries (minutos),
        da binária. Opcionais: market ("normal" | "otc"), next_open (fechado: quando abre) e next_close (aberto:
        quando fecha), em horário da corretora, e os mesmos dados da digital: binary, digital e digital_open
        (None = não sabe), digital_payout, digital_reason, digital_expiries, digital_next_open e
        digital_next_close. Pares só de digital vêm com binary False e open False. Nunca espera pela corretora."""
        return []

    def disconnect(self) -> None:
        """Fecha a conexão (ao trocar de login). Padrão: nada a fazer."""

    def currency(self) -> str:
        """Moeda da conta (a demo da IQ costuma ser em dólar)."""
        return "USD"

    def tradable(self, asset: str, kind: str = BINARY) -> tuple[bool, str]:
        """Dá para comprar opção de 1 min deste tipo neste ativo agora? Nunca espera pela corretora."""
        return (True, "ok") if kind == BINARY else (False, f"{asset}: esta corretora não tem digital")

    def payout_now(self, asset: str, kind: str = BINARY) -> float | None:
        """Payout atual da opção de 1 min deste tipo, do que já está em memória (nunca espera). None = não sabe."""
        return None

    def buy(self, asset: str, direction: str, amount: float, minutes: int = 1, kind: str = BINARY) -> OrderTicket:
        """Envia uma ordem (binária turbo ou digital). Levanta BrokerError se a corretora recusar."""
        raise BrokerError("Esta corretora não envia ordens")

    def order_result(self, ticket: OrderTicket) -> OrderResult | None:
        """Resultado da ordem, ou None se ela ainda não fechou."""
        raise BrokerError("Esta corretora não envia ordens")

    def subscribe_mood(self, asset: str, force: bool = False) -> bool:
        """Pede o sentimento dos traders deste par (uma vez por conexão; `force` pede de novo).
        False = esta corretora ou este par não tem."""
        return False

    def traders_mood(self, asset: str) -> tuple[float, float] | None:
        """(valor que a corretora mandou, segundos desde que ele chegou), do que já está em memória.
        Nunca espera. None = ainda não chegou nada nesta conexão."""
        return None
