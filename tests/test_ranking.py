# tests/test_ranking.py
from bot.backtest.ranking import rank_strategies
from bot.strategies.base import BuySignal, SellDecision


def candle(hi, lo):
    return {"avgHighPrice": hi, "avgLowPrice": lo,
            "highPriceVolume": 1000, "lowPriceVolume": 1000}


class Profitable:
    name = "profitable"
    def __init__(self): self.bought = False
    def find_buys(self, markets, budget):
        m = markets[0]
        if self.bought or budget < m.low: return []
        self.bought = True
        return [BuySignal(item_id=m.item_id, price=m.low, qty=1, reason="")]
    def should_sell(self, position, market):
        return SellDecision(sell=market.high >= 200, reason="")


class DoesNothing:
    name = "nothing"
    def find_buys(self, markets, budget): return []
    def should_sell(self, position, market): return SellDecision(sell=False, reason="")


def test_ranks_by_profit():
    candles = [candle(100, 100), candle(200, 190)]
    factories = {"profitable": Profitable, "nothing": DoesNothing}
    ranked = rank_strategies(factories, candles, budget=1000)
    assert [name for name, _ in ranked] == ["profitable", "nothing"]
    assert ranked[0][1].total_profit > 0
    assert ranked[1][1].total_profit == 0
