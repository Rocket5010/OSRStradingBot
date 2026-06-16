import pytest
from bot.strategies.base import Strategy, MarketData, BuySignal, SellDecision


def test_marketdata_holds_fields():
    md = MarketData(item_id=2, name="Cannonball", low=150, high=200,
                    vol_1h=5000, history=[], buy_limit=11000, members=False)
    assert md.item_id == 2 and md.high == 200
    assert md.buy_limit == 11000 and md.members is False


def test_marketdata_defaults():
    md = MarketData(item_id=2, name="X", low=1, high=2, vol_1h=0)
    assert md.history == [] and md.buy_limit == 0 and md.members is False


def test_buysignal_defaults():
    sig = BuySignal(item_id=2, price=150, qty=10, reason="cheap")
    assert sig.qty == 10 and sig.reason == "cheap"


def test_selldecision_sell_flag():
    d = SellDecision(sell=True, reason="target hit")
    assert d.sell is True


def test_strategy_is_abstract():
    with pytest.raises(TypeError):
        Strategy()  # cannot instantiate abstract base


def test_concrete_strategy_works():
    class Dummy(Strategy):
        name = "dummy"
        description = "test"
        def find_buys(self, market, budget):
            return [BuySignal(item_id=2, price=10, qty=1, reason="x")]
        def should_sell(self, position, market):
            return SellDecision(sell=False, reason="hold")
        def default_params(self):
            return {"min_margin": 50}

    d = Dummy()
    assert d.find_buys([], 1000)[0].item_id == 2
    assert d.should_sell(None, None).sell is False
    assert d.default_params()["min_margin"] == 50
