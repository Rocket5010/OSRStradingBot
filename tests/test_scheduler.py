# tests/test_scheduler.py
from bot import db, runs, positions as pos
from bot.scheduler import PollScheduler
from bot.strategies.base import BuySignal, SellDecision


class StubClient:
    def latest(self):
        return {"1": {"high": 150, "low": 100}}
    def one_hour(self):
        return {"1": {"highPriceVolume": 500, "lowPriceVolume": 500}}
    def timeseries(self, item_id, timestep):
        return []
    def mapping(self):
        return [{"id": 1, "name": "Item1", "limit": 1000, "members": False}]


class AlwaysBuy:
    name = "alwaysbuy"
    def __init__(self, **p): self.params = p
    def find_buys(self, markets, budget):
        return [BuySignal(item_id=m.item_id, price=m.low, qty=1, reason="x")
                for m in markets if budget >= m.low]
    def should_sell(self, position, market):
        return SellDecision(sell=False, reason="")


def loader_stub(_dir):
    return {"alwaysbuy": AlwaysBuy()}


def test_tick_polls_then_proposes():
    conn = db.connect(":memory:")
    db.init_db(conn)
    runs.start_run(conn, "alwaysbuy", budget_gp=10_000)
    sched = PollScheduler(conn, StubClient(), watchlist=[1], loader=loader_stub)
    sched.tick(now=0.0)
    # price_cache populated by poll, and a proposal created by evaluate
    assert conn.execute("SELECT COUNT(*) c FROM price_cache").fetchone()["c"] == 1
    assert len(pos.list_positions(conn, state="proposed")) == 1
