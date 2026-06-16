"""Pure technical indicators over a numeric price series. Stdlib only."""

import statistics


def price_series(candles):
    """Mid-price per candle; skips candles with missing prices."""
    out = []
    for c in candles:
        hi, lo = c.get("avgHighPrice"), c.get("avgLowPrice")
        if hi is None or lo is None:
            continue
        out.append((hi + lo) / 2)
    return out


def mean(series):
    return statistics.fmean(series)


def stdev(series):
    """Sample standard deviation."""
    return statistics.stdev(series)


def sma(series, window):
    """Simple moving average of the last `window` points, or None if too short."""
    if len(series) < window or window <= 0:
        return None
    return statistics.fmean(series[-window:])


def bollinger(series, period, k):
    """Return (lower, mid, upper) bands over the last `period` points."""
    if len(series) < period:
        return None
    window = series[-period:]
    mid = statistics.fmean(window)
    sd = statistics.stdev(window)
    return (mid - k * sd, mid, mid + k * sd)


def rsi(series, period):
    """Wilder-style RSI over the last `period` deltas; None if too short."""
    if len(series) < period + 1:
        return None
    deltas = [series[i] - series[i - 1] for i in range(1, len(series))]
    recent = deltas[-period:]
    gains = [d for d in recent if d > 0]
    losses = [-d for d in recent if d < 0]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def window_high(series, window):
    """Highest value in the last `window` points."""
    return max(series[-window:])
