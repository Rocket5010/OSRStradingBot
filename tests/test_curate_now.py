from bot import db, curator
from bot.curate_now import run
from bot.strategies.base import BuySignal, SellDecision


class StubStrat:
    name = "stubcur"
    def __init__(self, **p): self.bought = False
    def find_buys(self, markets, budget):
        m = markets[0]
        if self.bought or budget < m.low or m.item_id != 2:
            return []
        self.bought = True
        return [BuySignal(item_id=m.item_id, price=m.low, qty=1, reason="")]
    def should_sell(self, position, market):
        return SellDecision(sell=market.high >= 200, reason="")


class StubClient:
    def latest(self):
        return {"1": {"high": 110, "low": 100}, "2": {"high": 120, "low": 100}}
    def one_hour(self):
        return {"1": {"highPriceVolume": 5000, "lowPriceVolume": 5000},
                "2": {"highPriceVolume": 5000, "lowPriceVolume": 5000}}
    def timeseries(self, item_id, timestep):
        v = {"highPriceVolume": 1000, "lowPriceVolume": 1000}
        if item_id == 2:
            return [{"avgHighPrice": 100, "avgLowPrice": 100, **v},
                    {"avgHighPrice": 200, "avgLowPrice": 190, **v}]
        return [{"avgHighPrice": 100, "avgLowPrice": 100, **v},
                {"avgHighPrice": 100, "avgLowPrice": 100, **v}]


def loader_stub(_dir):
    return {"stubcur": StubStrat()}


def test_run_polls_screens_and_saves(monkeypatch):
    import bot.curate_now as cn
    monkeypatch.setattr(cn, "load_strategies", loader_stub)
    conn = db.connect(":memory:")
    db.init_db(conn)
    db.set_config(conn, "curate_strategy", "stubcur")
    picks = run(conn, StubClient(), cap=50, budget=1000, min_candles=2)
    assert 2 in picks                      # profitable item curated in
    assert curator.get_watchlist(conn) == picks   # saved to config


def test_run_raises_valueerror_on_unknown_strategy(monkeypatch):
    import bot.curate_now as cn
    import pytest
    monkeypatch.setattr(cn, "load_strategies", lambda d: {})  # no strategies
    conn = db.connect(":memory:")
    db.init_db(conn)
    db.set_config(conn, "curate_strategy", "nope")
    with pytest.raises(ValueError):
        cn.run(conn, StubClient())


class NeverBuy:
    name = "neverbuy"
    def __init__(self, **p): pass
    def find_buys(self, markets, budget):
        return []
    def should_sell(self, position, market):
        return SellDecision(sell=False, reason="")


def test_run_keeps_watchlist_when_no_picks(monkeypatch):
    import bot.curate_now as cn
    monkeypatch.setattr(cn, "load_strategies", lambda d: {"neverbuy": NeverBuy()})
    conn = db.connect(":memory:")
    db.init_db(conn)
    db.set_config(conn, "curate_strategy", "neverbuy")
    curator.save_watchlist(conn, [111, 222])      # existing good watchlist
    picks = run(conn, StubClient(), min_candles=1)
    assert picks == []
    assert curator.get_watchlist(conn) == [111, 222]   # not wiped
