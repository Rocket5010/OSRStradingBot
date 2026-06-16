# tests/test_rsi.py
from types import SimpleNamespace
from bot.strategies.base import MarketData
from bot.strategies.rsi import Rsi


def candles(prices):
    return [{"avgHighPrice": p, "avgLowPrice": p} for p in prices]


def md(low, high, hist):
    return MarketData(item_id=1, name="i", low=low, high=high, vol_1h=1000,
                      history=candles(hist), buy_limit=1000)


FALLING = list(range(30, 14, -1))   # strictly falling -> RSI 0 (oversold)
RISING = list(range(14, 30))        # strictly rising -> RSI 100 (overbought)


def test_buys_when_oversold():
    s = Rsi(rsi_period=14, lo=30, hi=70, min_vol=100)
    assert len(s.find_buys([md(low=10, high=11, hist=FALLING)], budget=10_000)) == 1


def test_no_buy_when_not_oversold():
    s = Rsi(rsi_period=14, lo=30, hi=70, min_vol=100)
    assert s.find_buys([md(low=10, high=11, hist=RISING)], budget=10_000) == []


def test_sell_when_overbought():
    s = Rsi(rsi_period=14, lo=30, hi=70, min_vol=100, stop_loss_pct=0.9)
    pos = SimpleNamespace(buy_price=10)
    assert s.should_sell(pos, md(low=28, high=29, hist=RISING)).sell is True
