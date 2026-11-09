from __future__ import annotations

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class CandleRow(Base):
    __tablename__ = "candles"

    asset: Mapped[str] = mapped_column(String(32), primary_key=True)
    timeframe: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[int] = mapped_column(Integer, primary_key=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float, default=0.0)


class MoodRow(Base):
    """Sentimento dos traders da IQ a cada 5 s (base de pesquisa), no mesmo relógio das velas de 5 s."""

    __tablename__ = "mood"

    asset: Mapped[str] = mapped_column(String(32), primary_key=True)
    ts: Mapped[int] = mapped_column(Integer, primary_key=True)
    value: Mapped[float] = mapped_column(Float)  # como a IQ manda (fração de 0 a 1)
    age: Mapped[float] = mapped_column(Float)  # segundos desde que a IQ mandou esse valor


class SessionRow(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[int] = mapped_column(Integer)
    stopped_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mode: Mapped[str] = mapped_column(String(16), default="paper")
    account: Mapped[str] = mapped_column(String(16), default="PRACTICE")
    asset: Mapped[str] = mapped_column(String(32))
    timeframe: Mapped[int] = mapped_column(Integer)
    payout: Mapped[float] = mapped_column(Float)
    stop_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)


class SignalRow(Base):
    """Um sinal de um script e o que aconteceu com ele (modo paper)."""

    __tablename__ = "signals"
    __table_args__ = (
        UniqueConstraint("asset", "timeframe", "strategy", "candle_ts", name="uq_signal"),
        Index("ix_signals_candle_ts", "candle_ts"),
        Index("ix_signals_result", "result"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("sessions.id"), nullable=True)
    origin: Mapped[str] = mapped_column(String(16))  # "backtest" (histórico) ou "ao_vivo"
    asset: Mapped[str] = mapped_column(String(32))
    timeframe: Mapped[int] = mapped_column(Integer)
    is_otc: Mapped[bool] = mapped_column(Boolean, default=False)
    strategy: Mapped[str] = mapped_column(String(48))
    direction: Mapped[str] = mapped_column(String(8))
    setup: Mapped[str] = mapped_column(String(64))
    candle_ts: Mapped[int] = mapped_column(Integer)  # vela que gerou o sinal
    entry_ts: Mapped[int] = mapped_column(Integer)  # vela da entrada (a seguinte)
    entry_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    result: Mapped[str] = mapped_column(String(16), default="pendente")
    payout: Mapped[float] = mapped_column(Float)
    profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[int] = mapped_column(Integer)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "origin": self.origin,
            "session_id": self.session_id,
            "asset": self.asset,
            "timeframe": self.timeframe,
            "is_otc": self.is_otc,
            "strategy": self.strategy,
            "direction": self.direction,
            "setup": self.setup,
            "candle_ts": self.candle_ts,
            "entry_ts": self.entry_ts,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "result": self.result,
            "payout": self.payout,
            "profit": self.profit,
            "details": self.details or {},
        }


class OrderRow(Base):
    """Ordem de verdade enviada à corretora (conta demo), depois de aprovada no painel."""

    __tablename__ = "orders"
    __table_args__ = (Index("ix_orders_requested_at", "requested_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    signal_id: Mapped[int | None] = mapped_column(ForeignKey("signals.id"), nullable=True)
    asset: Mapped[str] = mapped_column(String(32))
    timeframe: Mapped[int] = mapped_column(Integer)
    strategy: Mapped[str] = mapped_column(String(48))
    direction: Mapped[str] = mapped_column(String(8))
    amount: Mapped[float] = mapped_column(Float)
    gale: Mapped[int] = mapped_column(Integer, default=0)  # 0 = entrada normal; 1..2 = nível do martingale
    account: Mapped[str] = mapped_column(String(16), default="PRACTICE")
    # enviando | aberta | win | loss | empate | bloqueada | erro | sem_resultado
    status: Mapped[str] = mapped_column(String(16))
    broker_order_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requested_at: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ref_price: Mapped[float | None] = mapped_column(Float, nullable=True)  # preço no momento da decisão
    profit: Mapped[float | None] = mapped_column(Float, nullable=True)  # em dinheiro
    error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    option_type: Mapped[str] = mapped_column(String(8), default="binary")  # binary | digital

    def to_dict(self) -> dict:
        return {
            "id": self.id, "signal_id": self.signal_id, "asset": self.asset, "timeframe": self.timeframe,
            "strategy": self.strategy, "direction": self.direction, "amount": self.amount, "gale": self.gale or 0,
            "account": self.account, "option_type": self.option_type or "binary",
            "status": self.status, "broker_order_id": self.broker_order_id, "requested_at": self.requested_at,
            "expires_at": self.expires_at, "ref_price": self.ref_price, "profit": self.profit, "error": self.error,
        }
