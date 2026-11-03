"""Acesso ao SQLite. Um arquivo só (data/botbene.sqlite); dá para trocar por PostgreSQL
mudando a URL, porque tudo passa pelo SQLAlchemy."""

from __future__ import annotations

import time
from collections.abc import Iterable, Sequence
from pathlib import Path

from sqlalchemy import create_engine, event, func, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, CandleRow, OrderRow, SessionRow, SignalRow
from app.market.candle import Candle


def _by_strategy(q, strategy: str | Sequence[str] | None):
    """Filtra por uma estratégia ou por uma lista delas."""
    if not strategy:
        return q
    if isinstance(strategy, str):
        return q.where(SignalRow.strategy == strategy)
    return q.where(SignalRow.strategy.in_(list(strategy)))


class Database:
    def __init__(self, url: str) -> None:
        self.engine = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(self.engine, "connect")
        def _pragmas(dbapi_conn, _record):  # noqa: ANN001
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")  # leitura pelo painel enquanto o bot grava
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.close()

        Base.metadata.create_all(self.engine)
        self._add_missing_columns()
        self.Session = sessionmaker(self.engine, expire_on_commit=False)

    def _add_missing_columns(self) -> None:
        """create_all não altera tabelas que já existem: colunas novas entram aqui (SQLite)."""
        added = {"orders": {"gale": "INTEGER DEFAULT 0"}}
        with self.engine.begin() as conn:
            for table, cols in added.items():
                have = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
                for name, ddl in cols.items():
                    if have and name not in have:
                        conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")

    # ------------------------------------------------------------------ velas

    def save_candles(self, asset: str, timeframe: int, candles: Iterable[Candle]) -> None:
        rows = [
            {"asset": asset, "timeframe": timeframe, "ts": c.ts, "open": c.open, "high": c.high,
             "low": c.low, "close": c.close, "volume": c.volume}
            for c in candles
        ]
        with self.Session.begin() as s:
            for i in range(0, len(rows), 400):
                stmt = sqlite_insert(CandleRow).values(rows[i : i + 400])
                stmt = stmt.on_conflict_do_update(
                    index_elements=["asset", "timeframe", "ts"],
                    set_={k: stmt.excluded[k] for k in ("open", "high", "low", "close", "volume")},
                )
                s.execute(stmt)

    def load_candles(self, asset: str, timeframe: int, limit: int) -> list[Candle]:
        with self.Session() as s:
            q = (
                select(CandleRow)
                .where(CandleRow.asset == asset, CandleRow.timeframe == timeframe)
                .order_by(CandleRow.ts.desc())
                .limit(limit)
            )
            rows = list(s.scalars(q))
        return [Candle(r.ts, r.open, r.high, r.low, r.close, r.volume) for r in reversed(rows)]

    def candle_series(self) -> list[dict]:
        """Que velas existem no banco: ativo, tempo, quantidade, primeira e última."""
        with self.Session() as s:
            q = select(
                CandleRow.asset, CandleRow.timeframe, func.count(), func.min(CandleRow.ts), func.max(CandleRow.ts)
            ).group_by(CandleRow.asset, CandleRow.timeframe).order_by(CandleRow.asset, CandleRow.timeframe)
            return [{"asset": a, "timeframe": tf, "count": n, "first_ts": lo, "last_ts": hi} for a, tf, n, lo, hi in s.execute(q)]

    # ------------------------------------------------------------------ sessões

    def start_session(self, asset: str, timeframe: int, account: str, payout: float) -> int:
        with self.Session.begin() as s:
            row = SessionRow(started_at=int(time.time()), asset=asset, timeframe=timeframe, account=account, payout=payout)
            s.add(row)
            s.flush()
            return row.id

    def end_session(self, session_id: int, reason: str) -> None:
        with self.Session.begin() as s:
            s.execute(update(SessionRow).where(SessionRow.id == session_id).values(stopped_at=int(time.time()), stop_reason=reason))

    def last_session(self) -> SessionRow | None:
        with self.Session() as s:
            return s.scalars(select(SessionRow).order_by(SessionRow.id.desc()).limit(1)).first()

    # ------------------------------------------------------------------ sinais

    def add_signal(self, **fields) -> dict | None:
        """Grava o sinal se ainda não existir (mesmo ativo/tf/script/vela). Devolve o registro novo ou None."""
        fields.setdefault("created_at", int(time.time()))
        with self.Session.begin() as s:
            stmt = sqlite_insert(SignalRow).values(**fields).on_conflict_do_nothing(
                index_elements=["asset", "timeframe", "strategy", "candle_ts"]
            )
            res = s.execute(stmt)
            if not res.rowcount:
                return None
            row = s.scalars(
                select(SignalRow).where(
                    SignalRow.asset == fields["asset"],
                    SignalRow.timeframe == fields["timeframe"],
                    SignalRow.strategy == fields["strategy"],
                    SignalRow.candle_ts == fields["candle_ts"],
                )
            ).one()
            return row.to_dict()

    def pending_signals(self, asset: str, timeframe: int) -> list[dict]:
        with self.Session() as s:
            q = select(SignalRow).where(
                SignalRow.asset == asset, SignalRow.timeframe == timeframe, SignalRow.result == "pendente"
            )
            return [r.to_dict() for r in s.scalars(q)]

    def resolve_signal(
        self, signal_id: int, *, entry: float | None, exit_: float | None, result: str, profit: float, only_pending: bool = True
    ) -> bool:
        """Grava o resultado. Por padrão só mexe em sinal ainda pendente (bot e resolvedor nunca brigam)."""
        with self.Session.begin() as s:
            stmt = update(SignalRow).where(SignalRow.id == signal_id)
            if only_pending:
                stmt = stmt.where(SignalRow.result == "pendente")
            res = s.execute(stmt.values(entry_price=entry, exit_price=exit_, result=result, profit=profit))
            return bool(res.rowcount)

    def all_pending(self) -> list[dict]:
        with self.Session() as s:
            q = select(SignalRow).where(SignalRow.result == "pendente").order_by(SignalRow.entry_ts)
            return [r.to_dict() for r in s.scalars(q)]

    def list_signals(
        self,
        *,
        limit: int = 200,
        asset: str | None = None,
        strategy: str | Sequence[str] | None = None,
        origin: str | None = None,
        result: str | None = None,
        since_ts: int | None = None,
    ) -> list[dict]:
        with self.Session() as s:
            q = select(SignalRow)
            if asset:
                q = q.where(SignalRow.asset == asset)
            q = _by_strategy(q, strategy)
            if origin:
                q = q.where(SignalRow.origin == origin)
            if result:
                q = q.where(SignalRow.result == result)
            if since_ts is not None:
                q = q.where(SignalRow.candle_ts >= since_ts)
            q = q.order_by(SignalRow.candle_ts.desc(), SignalRow.id.desc()).limit(limit)
            return [r.to_dict() for r in s.scalars(q)]

    def resolved_signals(
        self,
        *,
        origin: str | None = None,
        asset: str | None = None,
        strategy: str | Sequence[str] | None = None,
        since_ts: int | None = None,
    ) -> Sequence[dict]:
        with self.Session() as s:
            q = select(SignalRow).where(SignalRow.result.in_(("win", "loss", "empate")))
            if origin:
                q = q.where(SignalRow.origin == origin)
            if asset:
                q = q.where(SignalRow.asset == asset)
            q = _by_strategy(q, strategy)
            if since_ts is not None:
                q = q.where(SignalRow.entry_ts >= since_ts)
            q = q.order_by(SignalRow.entry_ts)
            return [r.to_dict() for r in s.scalars(q)]

    def assets(self) -> list[str]:
        with self.Session() as s:
            return sorted(set(s.scalars(select(SignalRow.asset).distinct())))

    # ------------------------------------------------------------------ zerar o histórico

    def reset_history(self, backup_dir: Path) -> dict:
        """Guarda uma cópia do banco e apaga entradas, ordens, sessões e velas. Devolve o que foi apagado."""
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / f"botbene-{time.strftime('%Y%m%d-%H%M%S')}.sqlite"
        with self.engine.connect() as conn:
            conn.exec_driver_sql("VACUUM INTO ?", (str(backup),))
        counts = {}
        with self.engine.begin() as conn:
            # ordem por causa das chaves estrangeiras: ordens -> sinais -> sessões
            for table in ("orders", "signals", "sessions", "candles"):
                counts[table] = conn.exec_driver_sql(f"DELETE FROM {table}").rowcount
        with self.engine.connect() as conn:
            conn.exec_driver_sql("VACUUM")
        return {"apagado": counts, "copia": str(backup)}

    # ------------------------------------------------------------------ ordens (conta demo)

    def add_order(self, **fields) -> dict:
        fields.setdefault("requested_at", int(time.time()))
        with self.Session.begin() as s:
            row = OrderRow(**fields)
            s.add(row)
            s.flush()
            return row.to_dict()

    def update_order(self, order_id: int, **fields) -> dict | None:
        with self.Session.begin() as s:
            row = s.get(OrderRow, order_id)
            if row is None:
                return None
            for k, v in fields.items():
                setattr(row, k, v)
            s.flush()
            return row.to_dict()

    def list_orders(self, *, limit: int = 200, since_ts: int | None = None) -> list[dict]:
        with self.Session() as s:
            q = select(OrderRow)
            if since_ts is not None:
                q = q.where(OrderRow.requested_at >= since_ts)
            q = q.order_by(OrderRow.requested_at.desc(), OrderRow.id.desc()).limit(limit)
            return [r.to_dict() for r in s.scalars(q)]
