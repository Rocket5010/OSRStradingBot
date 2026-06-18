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
        if item_id == 2:
            return [{"avgHighPrice": 100, "avgLowPrice": 100},
                    {"avgHighPrice": 200, "avgLowPrice": 190}]
        return [{"avgHighPrice": 100, "avgLowPrice": 100},
                {"avgHighPrice": 100, "avgLowPrice": 100}]


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
