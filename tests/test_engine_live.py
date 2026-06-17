# tests/test_engine_live.py
import json
from bot import db, runs, positions as pos
from bot.engine_live import evaluate
from bot.strategies.base import MarketData, BuySignal, SellDecision


def fresh():
    conn = db.connect(":memory:")
    db.init_db(conn)
    return conn


class AlwaysBuy:
    name = "alwaysbuy"
    def __init__(self, **p): self.params = p
    def find_buys(self, markets, budget):
        out = []
        for m in markets:
            if budget >= m.low:
                out.append(BuySignal(item_id=m.item_id, price=m.low, qty=1, reason="x"))
                budget -= m.low
        return out
    def should_sell(self, position, market):
        return SellDecision(sell=market.high >= 200, reason="hit")


def loader_stub(_dir):
    return {"alwaysbuy": AlwaysBuy()}


def market(item_id, low, high):
    return MarketData(item_id=item_id, name=f"i{item_id}", low=low, high=high,
                      vol_1h=1000, history=[], buy_limit=1000)


def test_creates_proposals_within_budget():
    conn = fresh()
    rid = runs.start_run(conn, "alwaysbuy", budget_gp=250)
    markets = {1: market(1, 100, 150), 2: market(2, 100, 150)}
    evaluate(conn, markets, now=0.0, loader=loader_stub)
    proposed = pos.list_positions(conn, state="proposed")
    assert len(proposed) == 2
    assert all(p["run_id"] == rid for p in proposed)


def test_skips_duplicate_open_position():
    conn = fresh()
    rid = runs.start_run(conn, "alwaysbuy", budget_gp=10_000)
    markets = {1: market(1, 100, 150)}
    evaluate(conn, markets, now=0.0, loader=loader_stub)
    evaluate(conn, markets, now=0.0, loader=loader_stub)   # second pass
    assert len(pos.list_positions(conn, state="proposed")) == 1


def test_stopped_run_produces_nothing():
    conn = fresh()
    rid = runs.start_run(conn, "alwaysbuy", budget_gp=10_000)
    runs.stop_run(conn, rid)
    evaluate(conn, {1: market(1, 100, 150)}, now=0.0, loader=loader_stub)
    assert pos.list_positions(conn) == []


def test_sell_recommendation_for_filled():
    conn = fresh()
    rid = runs.start_run(conn, "alwaysbuy", budget_gp=10_000)
    pid = pos.create_proposed(conn, strategy="alwaysbuy", item_id=1, item_name="i1",
                              buy_price=100, qty=1, run_id=rid)
    pos.accept(conn, pid); pos.mark_filled(conn, pid)
    evaluate(conn, {1: market(1, 180, 220)}, now=0.0, loader=loader_stub)  # high>=200
    sigs = conn.execute("SELECT * FROM signals WHERE type='sell'").fetchall()
    assert len(sigs) == 1 and sigs[0]["item_id"] == 1
    # idempotent: a second pass does not duplicate the sell signal
    evaluate(conn, {1: market(1, 180, 220)}, now=0.0, loader=loader_stub)
    assert len(conn.execute("SELECT * FROM signals WHERE type='sell'").fetchall()) == 1


def test_high_water_raised_for_filled():
    conn = fresh()
    rid = runs.start_run(conn, "alwaysbuy", budget_gp=10_000)
    pid = pos.create_proposed(conn, strategy="alwaysbuy", item_id=1, item_name="i1",
                              buy_price=100, qty=1, run_id=rid)
    pos.accept(conn, pid); pos.mark_filled(conn, pid)
    evaluate(conn, {1: market(1, 150, 190)}, now=0.0, loader=loader_stub)
    assert pos.get(conn, pid)["high_water"] == 190
