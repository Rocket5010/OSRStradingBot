# tests/test_bollinger.py
from types import SimpleNamespace
from bot.strategies.base import MarketData
from bot.strategies.bollinger import Bollinger


def candles(prices):
    return [{"avgHighPrice": p, "avgLowPrice": p} for p in prices]


def md(low, high, hist):
    return MarketData(item_id=1, name="i", low=low, high=high, vol_1h=1000,
                      history=candles(hist), buy_limit=1000)


HIST = [10, 12, 14, 12, 10, 12, 14, 12, 10, 12]  # mid 11.8


def test_buys_at_lower_band():
    s = Bollinger(period=10, k=2.0, min_vol=100)
    assert len(s.find_buys([md(low=8, high=9, hist=HIST)], budget=10_000)) == 1


def test_no_buy_above_lower_band():
    s = Bollinger(period=10, k=2.0, min_vol=100)
    assert s.find_buys([md(low=12, high=13, hist=HIST)], budget=10_000) == []


def test_sell_at_mid_band():
    s = Bollinger(period=10, k=2.0, min_vol=100, stop_loss_pct=0.5)
    pos = SimpleNamespace(buy_price=8)
    assert s.should_sell(pos, md(low=12, high=13, hist=HIST)).sell is True
