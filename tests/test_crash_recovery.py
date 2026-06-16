from types import SimpleNamespace
from bot.strategies.base import MarketData
from bot.strategies.crash_recovery import CrashRecovery


def candles(prices):
    return [{"avgHighPrice": p, "avgLowPrice": p} for p in prices]


def md(low, high, hist):
    return MarketData(item_id=1, name="i", low=low, high=high, vol_1h=1000,
                      history=candles(hist), buy_limit=1000)


# reference high ~100, stable floor ~95; current 80 = 20% below ref
STABLE = [100, 98, 96, 100, 97, 95, 99, 96, 100, 98]


def test_buys_after_crash():
    s = CrashRecovery(drop_pct=0.15, floor_lookback=10, min_vol=100)
    assert len(s.find_buys([md(low=80, high=81, hist=STABLE)], budget=10_000)) == 1


def test_no_buy_without_crash():
    s = CrashRecovery(drop_pct=0.15, floor_lookback=10, min_vol=100)
    assert s.find_buys([md(low=99, high=100, hist=STABLE)], budget=10_000) == []


def test_sell_on_recovery():
    s = CrashRecovery(drop_pct=0.15, floor_lookback=10, min_vol=100,
                      stop_loss_pct=0.5, recover_pct=0.9)
    pos = SimpleNamespace(buy_price=80)
    # reference ~100; recover target 0.9*100=90; high 92 >= 90
    assert s.should_sell(pos, md(low=91, high=92, hist=STABLE)).sell is True
