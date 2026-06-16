# tests/test_mean_reversion.py
from types import SimpleNamespace
from bot.strategies.base import MarketData
from bot.strategies.mean_reversion import MeanReversion


def candles(prices):
    return [{"avgHighPrice": p, "avgLowPrice": p} for p in prices]


def md(low, high, hist, vol=1000, limit=1000):
    return MarketData(item_id=1, name="i", low=low, high=high, vol_1h=vol,
                      history=candles(hist), buy_limit=limit)


def test_buys_when_below_band():
    s = MeanReversion(lookback=5, k=1.0, min_vol=100)
    # history mean ~100, stdev>0; current low well below band
    m = md(low=80, high=82, hist=[100, 110, 90, 105, 95])
    buys = s.find_buys([m], budget=10_000)
    assert len(buys) == 1


def test_no_buy_when_within_band():
    s = MeanReversion(lookback=5, k=1.0, min_vol=100)
    m = md(low=100, high=102, hist=[100, 110, 90, 105, 95])
    assert s.find_buys([m], budget=10_000) == []


def test_sell_at_mean():
    s = MeanReversion(lookback=5, k=1.0, min_vol=100, stop_loss_pct=0.2)
    pos = SimpleNamespace(buy_price=80)
    m = md(low=99, high=101, hist=[100, 110, 90, 105, 95])  # mean 100, high>=mean
    assert s.should_sell(pos, m).sell is True


def test_sell_on_stop_loss():
    s = MeanReversion(lookback=5, k=1.0, min_vol=100, stop_loss_pct=0.1)
    pos = SimpleNamespace(buy_price=80)
    m = md(low=70, high=71, hist=[100, 110, 90, 105, 95])   # high 71 <= 72
    assert s.should_sell(pos, m).sell is True
