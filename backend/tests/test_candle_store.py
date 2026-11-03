from app.market.candle import Candle
from app.market.store import CandleStore


def c(ts: int, close: float) -> Candle:
    return Candle(ts=ts, open=1.0, high=max(1.0, close), low=min(1.0, close), close=close)


def test_forming_candle_updates_until_next_one_arrives():
    store = CandleStore("EURUSD", 60)
    assert store.ingest(c(60, 1.1)) == []
    assert store.ingest(c(60, 1.2)) == []  # mesma vela, atualização do stream
    closed = store.ingest(c(120, 1.3))
    assert closed == [c(60, 1.2)]  # fecha com o último valor recebido
    assert store.forming == c(120, 1.3)


def test_late_updates_of_closed_candle_are_ignored():
    store = CandleStore("EURUSD", 60)
    store.load_history([c(0, 1.0), c(60, 1.1)])
    assert store.ingest(c(60, 9.9)) == []
    assert store.closed[-1].close == 1.1


def test_close_forming_when_time_is_over():
    store = CandleStore("EURUSD", 60)
    store.ingest(c(60, 1.1))
    assert store.close_forming_if_expired(119) == []
    assert store.close_forming_if_expired(120) == [c(60, 1.1)]
    assert store.forming is None
    assert store.ingest(c(60, 2.0)) == []  # chegou atrasada: ignorada
