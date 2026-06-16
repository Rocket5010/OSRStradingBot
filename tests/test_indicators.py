import pytest
from bot.strategies import indicators as ind


def test_price_series_skips_none():
    candles = [
        {"avgHighPrice": 200, "avgLowPrice": 100},   # mid 150
        {"avgHighPrice": None, "avgLowPrice": None},  # skipped
        {"avgHighPrice": 220, "avgLowPrice": 180},   # mid 200
    ]
    assert ind.price_series(candles) == [150.0, 200.0]


def test_sma_last_window():
    assert ind.sma([1, 2, 3, 4, 5], 2) == 4.5   # mean of last 2


def test_sma_none_when_too_short():
    assert ind.sma([1, 2], 5) is None


def test_mean_and_stdev():
    assert ind.mean([2, 4, 6]) == 4.0
    assert round(ind.stdev([2, 4, 6]), 4) == 2.0   # population stdev


def test_bollinger_bands():
    series = [10, 12, 14, 12, 10, 12, 14, 12, 10, 12]
    lower, mid, upper = ind.bollinger(series, period=10, k=2)
    assert round(mid, 1) == 11.8
    assert lower < mid < upper


def test_rsi_all_gains_is_100():
    series = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
    assert ind.rsi(series, period=14) == 100.0


def test_rsi_none_when_too_short():
    assert ind.rsi([1, 2, 3], period=14) is None


def test_window_high():
    assert ind.window_high([5, 9, 3, 7], 3) == 9   # max of last 3
