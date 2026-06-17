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
