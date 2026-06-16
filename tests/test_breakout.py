from types import SimpleNamespace
from bot.strategies.base import MarketData
from bot.strategies.breakout import Breakout


def candles(prices, vol=100):
    return [{"avgHighPrice": p, "avgLowPrice": p,
             "highPriceVolume": vol, "lowPriceVolume": vol} for p in prices]


def md(low, high, hist, vol_1h):
    return MarketData(item_id=1, name="i", low=low, high=high, vol_1h=vol_1h,
                      history=hist, buy_limit=1000)


CHANNEL = candles([10, 11, 10, 12, 11, 10, 12, 11], vol=100)  # prior high 12


def test_buys_on_breakout_with_volume():
    s = Breakout(channel_days=8, vol_mult=2.0, min_vol=100)
    # current high 15 > prior high 12; vol_1h 500 > 2*200(=high+low vol per candle)
    m = md(low=14, high=15, hist=CHANNEL, vol_1h=500)
    assert len(s.find_buys([m], budget=10_000)) == 1


def test_no_buy_without_breakout():
    s = Breakout(channel_days=8, vol_mult=2.0, min_vol=100)
    m = md(low=11, high=12, hist=CHANNEL, vol_1h=500)   # 12 not above prior high 12
    assert s.find_buys([m], budget=10_000) == []


def test_no_buy_without_volume_spike():
    s = Breakout(channel_days=8, vol_mult=2.0, min_vol=100)
    m = md(low=14, high=15, hist=CHANNEL, vol_1h=150)   # below 2*avg vol
    assert s.find_buys([m], budget=10_000) == []


def test_trailing_stop_sells():
    s = Breakout(channel_days=8, vol_mult=2.0, min_vol=100, trail_pct=0.1)
    pos = SimpleNamespace(buy_price=14, high_water=20)
    # trailing stop = 20*0.9 = 18; high 17 <= 18 -> sell
    assert s.should_sell(pos, md(low=16, high=17, hist=CHANNEL, vol_1h=100)).sell is True


def test_trailing_stop_holds():
    s = Breakout(channel_days=8, vol_mult=2.0, min_vol=100, trail_pct=0.1)
    pos = SimpleNamespace(buy_price=14, high_water=20)
    assert s.should_sell(pos, md(low=18, high=19, hist=CHANNEL, vol_1h=100)).sell is False
