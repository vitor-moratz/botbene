"""Base de pesquisa num SQLite separado (data/research.sqlite), para não pesar o banco do bot.

A IQ guarda velas de 5 s só de ~1 semana para trás; as de 1 min vão bem mais longe.
"""

from __future__ import annotations

from collections.abc import Callable

from app.broker.base import Broker
from app.config import Settings
from app.db.database import Database
from app.market.candle import Candle

# Instrumentos de binária ("-op"): os mesmos que o bot lê e opera. A primeira pesquisa (nov/2026) usou
# os nomes sem sufixo, que na IQ são outro instrumento, com preço um pouco diferente.
DEFAULT_ASSETS = ("EURUSD-op", "GBPUSD-op", "USDJPY-op", "AUDUSD-op", "EURJPY-op", "EURGBP-op")
SUB_TF = 5
BATCH = 1000


def research_db(settings: Settings) -> Database:
    path = settings.resolved_data_dir() / "research.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    return Database(f"sqlite:///{path}")


def download(
    broker: Broker,
    db: Database,
    asset: str,
    timeframe: int,
    since_ts: int,
    end_ts: int,
    progress: Callable[[str, int, int, int], None] | None = None,
) -> int:
    """Baixa de trás para frente, de `end_ts` até `since_ts`, gravando lote a lote (se cair no meio,
    o que veio fica salvo). Para quando a corretora não tem mais velas daquele tempo."""
    total = 0
    end = end_ts
    oldest: int | None = None
    while True:
        # end_ts = 1ª vela do lote anterior + tf - 1: repete essa vela (upsert) e garante progresso
        # tanto se a corretora devolve "começou até end" quanto "fechou até end".
        candles = [c for c in broker.get_candles(asset, timeframe, BATCH, end_ts=end) if c.ts >= since_ts]
        if oldest is not None:
            candles = [c for c in candles if c.ts < oldest]
        if not candles:
            break
        db.save_candles(asset, timeframe, candles)
        total += len(candles)
        oldest = candles[0].ts
        if progress:
            progress(asset, timeframe, total, oldest)
        if oldest <= since_ts:
            break
        end = oldest + timeframe - 1
    return total


def load(db: Database, asset: str, timeframe: int) -> list[Candle]:
    return db.load_candles(asset, timeframe, 10_000_000)
