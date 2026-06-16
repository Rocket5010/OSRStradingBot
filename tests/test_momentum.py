from types import SimpleNamespace
from bot.strategies.base import MarketData
from bot.strategies.momentum import Momentum


def candles(prices):
    return [{"avgHighPrice": p, "avgLowPrice": p} for p in prices]


def md(low, high, hist):
    return MarketData(item_id=1, name="i", low=low, high=high, vol_1h=1000,
                      history=candles(hist), buy_limit=1000)


RISING = [10, 11, 12, 13, 14]
FLAT = [10, 11, 12, 13, 13]


def test_buys_on_rising_run():
    s = Momentum(lookback=4, min_vol=100)
    assert len(s.find_buys([md(low=14, high=15, hist=RISING)], budget=10_000)) == 1


def test_no_buy_when_not_rising():
    s = Momentum(lookback=4, min_vol=100)
    assert s.find_buys([md(low=13, high=14, hist=FLAT)], budget=10_000) == []


def test_sell_when_trend_flattens():
    s = Momentum(lookback=4, min_vol=100, stop_loss_pct=0.9)
    pos = SimpleNamespace(buy_price=10)
    assert s.should_sell(pos, md(low=13, high=14, hist=FLAT)).sell is True
