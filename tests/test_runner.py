# tests/test_runner.py
from bot.backtest.runner import run_ranking
from bot.strategies.base import BuySignal, SellDecision


class StubClient:
    def __init__(self, candles):
        self._candles = candles
        self.requested = []
    def timeseries(self, item_id, timestep):
        self.requested.append((item_id, timestep))
        return self._candles


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


def test_run_ranking_fetches_and_ranks():
    candles = [{"avgHighPrice": 100, "avgLowPrice": 100,
                "highPriceVolume": 1000, "lowPriceVolume": 1000},
               {"avgHighPrice": 200, "avgLowPrice": 190,
                "highPriceVolume": 1000, "lowPriceVolume": 1000}]
    client = StubClient(candles)
    ranked = run_ranking(client, item_id=2, factories={"profitable": Profitable},
                         budget=1000, timestep="24h")
    assert client.requested == [(2, "24h")]
    assert ranked[0][0] == "profitable"
    assert ranked[0][1].total_profit > 0


def test_run_ranking_empty_history_returns_zero_trades():
    client = StubClient([])
    ranked = run_ranking(client, item_id=2, factories={"profitable": Profitable},
                         budget=1000, timestep="24h")
    assert ranked[0][1].n_trades == 0
