import pytest

from app.indicators.core import change, ema, highest, lowest, rma, rsi, sma, true_range


def test_change_and_sma():
    assert change([1.0, 3.0, 2.0]) == [None, 2.0, -1.0]
    assert sma([1.0, 2.0, 3.0, 4.0], 2) == [None, 1.5, 2.5, 3.5]


def test_ema_seeds_with_first_value():
    out = ema([1.0, 2.0, 3.0], 2)
    assert out[0] == 1.0
    assert out[1] == pytest.approx(1 + 2 / 3)
    assert out[2] == pytest.approx(out[1] + 2 / 3 * (3 - out[1]))


def test_rma_seeds_with_sma():
    assert rma([1.0, 2.0, 3.0, 4.0], 2) == [None, 1.5, 2.25, 3.125]


def test_rma_skips_leading_none():
    assert rma([None, 2.0, 4.0, 6.0], 2) == [None, None, 3.0, 4.5]


def test_rsi_extremes():
    up = rsi([float(i) for i in range(20)], 14)
    down = rsi([float(-i) for i in range(20)], 14)
    assert up[14] == 100.0 and up[0] is None
    assert down[14] == 0.0


def test_true_range_uses_previous_close():
    assert true_range([2.0, 5.0], [1.0, 4.0], [1.5, 4.5]) == [1.0, 3.5]


def test_highest_lowest_windows():
    vals = [1.0, 3.0, 2.0, 5.0]
    assert highest(vals, 2) == [None, 3.0, 3.0, 5.0]
    assert lowest(vals, 3) == [None, None, 1.0, 2.0]
