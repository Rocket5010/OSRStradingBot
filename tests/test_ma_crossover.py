from types import SimpleNamespace
from bot.strategies.base import MarketData
from bot.strategies.ma_crossover import MaCrossover


def candles(prices):
    return [{"avgHighPrice": p, "avgLowPrice": p} for p in prices]


def md(low, high, hist):
    return MarketData(item_id=1, name="i", low=low, high=high, vol_1h=1000,
                      history=candles(hist), buy_limit=1000)


UPTREND = [10, 10, 10, 10, 10, 11, 12, 13, 14, 15]    # fast(3) > slow(8)
DOWNTREND = [15, 14, 13, 12, 11, 10, 9, 8, 7, 6]       # fast(3) < slow(8)


def test_buys_on_golden_cross():
    s = MaCrossover(fast_ma=3, slow_ma=8, min_vol=100)
    assert len(s.find_buys([md(low=15, high=16, hist=UPTREND)], budget=10_000)) == 1


def test_no_buy_on_downtrend():
    s = MaCrossover(fast_ma=3, slow_ma=8, min_vol=100)
    assert s.find_buys([md(low=6, high=7, hist=DOWNTREND)], budget=10_000) == []


def test_sell_on_death_cross():
    s = MaCrossover(fast_ma=3, slow_ma=8, min_vol=100, stop_loss_pct=0.9)
    pos = SimpleNamespace(buy_price=6)
    assert s.should_sell(pos, md(low=6, high=7, hist=DOWNTREND)).sell is True
