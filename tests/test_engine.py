# tests/test_engine.py
from bot.backtest.engine import run_backtest, BacktestResult


def candle(hi, lo, vol=1000):
    return {"avgHighPrice": hi, "avgLowPrice": lo,
            "highPriceVolume": vol, "lowPriceVolume": vol}


class BuyOnceSellHigh:
    """Stub: buys 1 unit on the first opportunity, sells when high >= 120."""
    name = "stub"

    def __init__(self):
        self.bought = False

    def find_buys(self, markets, budget):
        from bot.strategies.base import BuySignal
        m = markets[0]
        if self.bought or budget < m.low:
            return []
        self.bought = True
        return [BuySignal(item_id=m.item_id, price=m.low, qty=1, reason="stub")]

    def should_sell(self, position, market):
        from bot.strategies.base import SellDecision
        return SellDecision(sell=market.high >= 120, reason="stub")


def test_buy_then_sell_profit_after_tax():
    # buy at low=100 on candle 0; candle 1 high=120 triggers sell.
    candles = [candle(hi=105, lo=100), candle(hi=120, lo=118)]
    res = run_backtest(BuyOnceSellHigh(), candles, budget=1000)
    assert isinstance(res, BacktestResult)
    assert res.n_trades == 1
    # sell at 120, tax = floor(120*0.02)=2, proceeds=118, cost=100 -> pl=18
    assert res.trades[0]["pl"] == 18
    assert res.total_profit == 18


def test_slippage_reduces_profit():
    # buy at low=100 candle 0; sell at high=120 candle 1.
    candles = [candle(hi=105, lo=100), candle(hi=120, lo=118)]
    base = run_backtest(BuyOnceSellHigh(), candles, budget=1000)
    slipped = run_backtest(BuyOnceSellHigh(), candles, budget=1000, slippage=0.05)
    # buy 100->105, sell 120->114, tax floor(114*0.02)=2 -> pl=114-2-105=7
    assert slipped.trades[0]["buy_price"] == 105
    assert slipped.trades[0]["sell_price"] == 114
    assert slipped.total_profit < base.total_profit


def test_skips_none_price_candles():
    candles = [{"avgHighPrice": None, "avgLowPrice": None,
                "highPriceVolume": 0, "lowPriceVolume": 0},
               candle(hi=105, lo=100), candle(hi=120, lo=118)]
    res = run_backtest(BuyOnceSellHigh(), candles, budget=1000)
    assert res.n_trades == 1


def test_max_hold_forces_close():
    # never hits sell signal (high stays < 120); max_hold_steps=1 forces close.
    candles = [candle(hi=105, lo=100), candle(hi=106, lo=104), candle(hi=107, lo=105)]
    res = run_backtest(BuyOnceSellHigh(), candles, budget=1000, max_hold_steps=1)
    assert res.n_trades == 1  # forced close, not left open
    # opened at index 0, max_hold_steps=1 -> closes at index 1 (high=106)
    assert res.trades[0]["sell_price"] == 106


def test_open_position_liquidated_at_end():
    candles = [candle(hi=105, lo=100), candle(hi=106, lo=104)]
    res = run_backtest(BuyOnceSellHigh(), candles, budget=1000)
    assert res.n_trades == 1  # closed via end-of-data liquidation


def test_final_equity_equals_budget_plus_profit():
    candles = [candle(hi=105, lo=100), candle(hi=120, lo=118)]
    res = run_backtest(BuyOnceSellHigh(), candles, budget=1000)
    assert res.final_equity == 1000 + res.total_profit


def test_no_compounding_constant_qty():
    # A strategy that always sizes by the budget and round-trips every candle.
    # Before the fix, qty grew with cash (compounding) -> exponential blowup.
    # After the fix it sizes from a fixed budget, so every trade has equal qty.
    from bot.strategies.base import BuySignal, SellDecision
    from bot.strategies.sizing import size_qty

    class FixedFlipper:
        name = "ff"
        def __init__(self, **p): pass
        def find_buys(self, markets, budget):
            m = markets[0]
            q = size_qty(m.low, budget, m.buy_limit)
            return [BuySignal(item_id=m.item_id, price=m.low, qty=q, reason="")] if q > 0 else []
        def should_sell(self, position, market):
            return SellDecision(sell=market.high > position.buy_price, reason="")

    # every candle: buy at 100, sellable at 110 next candle; plenty of volume
    candles = [candle(hi=110, lo=100, vol=10**9) for _ in range(8)]
    res = run_backtest(FixedFlipper(), candles, budget=1_000_000)
    qtys = {t["qty"] for t in res.trades}
    assert res.n_trades >= 3
    assert len(qtys) == 1            # constant qty -> no compounding


def test_volume_caps_quantity():
    from bot.strategies.base import BuySignal, SellDecision

    class BigBuyer:
        name = "bb"
        def __init__(self, **p): self.bought = False
        def find_buys(self, markets, budget):
            if self.bought: return []
            self.bought = True
            return [BuySignal(item_id=1, price=1, qty=10**9, reason="")]  # absurd qty
        def should_sell(self, position, market):
            return SellDecision(sell=True, reason="")

    # candle volume total = 50+50 = 100; qty must be capped to 100
    candles = [candle(hi=2, lo=1, vol=50), candle(hi=3, lo=2, vol=50)]
    res = run_backtest(BigBuyer(), candles, budget=10**12)
    assert res.trades[0]["qty"] == 100


def test_buy_limit_caps_per_candle_accumulation():
    from bot.strategies.base import BuySignal, SellDecision

    class BigBuyer:
        name = "bb"
        def __init__(self, **p): self.bought = False
        def find_buys(self, markets, budget):
            if self.bought: return []
            self.bought = True
            return [BuySignal(item_id=1, price=1, qty=10**9, reason="")]
        def should_sell(self, position, market):
            return SellDecision(sell=True, reason="")

    # buy_limit 10, 24h candle -> 24/4 = 6 windows -> max 60 per candle, even
    # though volume (10^9) and budget are huge.
    candles = [candle(hi=2, lo=1, vol=10**9), candle(hi=3, lo=2, vol=10**9)]
    res = run_backtest(BigBuyer(), candles, budget=10**12, buy_limit=10,
                       candle_hours=24)
    assert res.trades[0]["qty"] == 60


def test_buy_limit_zero_means_no_limit():
    from bot.strategies.base import BuySignal, SellDecision

    class BigBuyer:
        name = "bb"
        def __init__(self, **p): self.bought = False
        def find_buys(self, markets, budget):
            if self.bought: return []
            self.bought = True
            return [BuySignal(item_id=1, price=1, qty=10**9, reason="")]
        def should_sell(self, position, market):
            return SellDecision(sell=True, reason="")

    candles = [candle(hi=2, lo=1, vol=80), candle(hi=3, lo=2, vol=80)]
    res = run_backtest(BigBuyer(), candles, budget=10**12, buy_limit=0)
    assert res.trades[0]["qty"] == 160   # capped by volume only
