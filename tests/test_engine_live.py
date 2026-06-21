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


class GreedyBuy:
    """Returns a signal for EVERY market item, ignoring budget (engine must cap)."""
    name = "greedy"
    def __init__(self, **p): self.params = p
    def find_buys(self, markets, budget):
        return [BuySignal(item_id=m.item_id, price=m.low, qty=1, reason="x")
                for m in markets]
    def should_sell(self, position, market):
        return SellDecision(sell=False, reason="")


def greedy_loader(_dir):
    return {"greedy": GreedyBuy()}


def test_engine_caps_total_proposals_at_budget():
    conn = fresh()
    runs.start_run(conn, "greedy", budget_gp=250)
    markets = {1: market(1, 100, 150), 2: market(2, 100, 150), 3: market(3, 100, 150)}
    evaluate(conn, markets, now=0.0, loader=greedy_loader)
    proposed = pos.list_positions(conn, state="proposed")
    total = sum(p["buy_price"] * p["qty"] for p in proposed)
    assert total <= 250
    # second pass must not exceed budget either (proposals count against it)
    evaluate(conn, markets, now=0.0, loader=greedy_loader)
    proposed = pos.list_positions(conn, state="proposed")
    assert sum(p["buy_price"] * p["qty"] for p in proposed) <= 250


def test_new_position_gets_fresh_sell_signal():
    conn = fresh()
    rid = runs.start_run(conn, "alwaysbuy", budget_gp=10_000)
    # first filled position, sells
    pid1 = pos.create_proposed(conn, strategy="alwaysbuy", item_id=1, item_name="i1",
                               buy_price=100, qty=1, run_id=rid)
    pos.accept(conn, pid1); pos.mark_filled(conn, pid1)
    evaluate(conn, {1: market(1, 180, 220)}, now=0.0, loader=loader_stub)
    pos.start_selling(conn, pid1); pos.mark_sold(conn, pid1, 220)
    # a NEW filled position for the same item+strategy
    pid2 = pos.create_proposed(conn, strategy="alwaysbuy", item_id=1, item_name="i1",
                               buy_price=100, qty=1, run_id=rid)
    pos.accept(conn, pid2); pos.mark_filled(conn, pid2)
    evaluate(conn, {1: market(1, 180, 220)}, now=0.0, loader=loader_stub)
    sigs = conn.execute("SELECT * FROM signals WHERE type='sell'").fetchall()
    assert len(sigs) == 2  # one per position, not blocked by the old signal


class BuysOnlyItem2:
    """Only ever wants item 2; never item 1."""
    name = "onlytwo"
    def __init__(self, **p): self.params = p
    def find_buys(self, markets, budget):
        out = []
        for m in markets:
            if m.item_id == 2 and budget >= m.low:
                out.append(BuySignal(item_id=2, price=m.low, qty=1, reason="x"))
        return out
    def should_sell(self, position, market):
        return SellDecision(sell=False, reason="")


def onlytwo_loader(_dir):
    return {"onlytwo": BuysOnlyItem2()}


def test_stale_proposal_is_dismissed():
    conn = fresh()
    rid = runs.start_run(conn, "onlytwo", budget_gp=10_000)
    # a proposed buy for item 1, which the strategy no longer wants
    pid = pos.create_proposed(conn, strategy="onlytwo", item_id=1, item_name="i1",
                              buy_price=100, qty=1, run_id=rid)
    evaluate(conn, {1: market(1, 100, 150)}, now=0.0, loader=onlytwo_loader)
    assert pos.get(conn, pid)["state"] == "dismissed"


def test_valid_proposal_is_kept():
    conn = fresh()
    rid = runs.start_run(conn, "onlytwo", budget_gp=10_000)
    pid = pos.create_proposed(conn, strategy="onlytwo", item_id=2, item_name="i2",
                              buy_price=100, qty=1, run_id=rid)
    evaluate(conn, {2: market(2, 100, 150)}, now=0.0, loader=onlytwo_loader)
    assert pos.get(conn, pid)["state"] == "proposed"


def test_proposal_without_market_data_is_kept():
    conn = fresh()
    rid = runs.start_run(conn, "onlytwo", budget_gp=10_000)
    pid = pos.create_proposed(conn, strategy="onlytwo", item_id=1, item_name="i1",
                              buy_price=100, qty=1, run_id=rid)
    evaluate(conn, {}, now=0.0, loader=onlytwo_loader)   # no market data at all
    assert pos.get(conn, pid)["state"] == "proposed"


def test_make_strategy_caches_loader():
    import bot.engine_live as el
    el._strategy_cache.clear()
    calls = []
    def counting_loader(d):
        calls.append(d)
        return {"alwaysbuy": AlwaysBuy()}
    el._make_strategy("alwaysbuy", {}, counting_loader)
    el._make_strategy("alwaysbuy", {}, counting_loader)
    assert len(calls) == 1                      # loader invoked once, then cached
    el._strategy_cache.clear()                  # don't leak into other tests


class ParamSell:
    name = "paramsell"
    def __init__(self, **p):
        self.params = {"sell_at": p.get("sell_at", 999999)}
    def find_buys(self, markets, budget):
        return []
    def should_sell(self, position, market):
        return SellDecision(sell=market.high >= self.params["sell_at"], reason="hit")


def paramsell_loader(_dir):
    return {"paramsell": ParamSell()}


def test_min_margin_gate_skips_thin_spread():
    conn = fresh()
    db.set_config(conn, "min_margin_gp", "50")
    rid = runs.start_run(conn, "alwaysbuy", budget_gp=10_000_000)
    # market: low 100, high 110 -> margin = 110 - tax(2) - 100 = 8 < 50 -> skip
    evaluate(conn, {1: market(1, 100, 110)}, now=0.0, loader=loader_stub)
    assert pos.list_positions(conn, state="proposed") == []


def test_min_margin_gate_allows_wide_spread():
    conn = fresh()
    db.set_config(conn, "min_margin_gp", "50")
    rid = runs.start_run(conn, "alwaysbuy", budget_gp=10_000_000)
    # low 100, high 200 -> margin = 200 - tax(4) - 100 = 96 >= 50 -> allowed
    evaluate(conn, {1: market(1, 100, 200)}, now=0.0, loader=loader_stub)
    assert len(pos.list_positions(conn, state="proposed")) == 1


def _mkt(item_id, low, high, high_time=None, low_time=None, history=None):
    return MarketData(item_id=item_id, name=f"i{item_id}", low=low, high=high,
                      vol_1h=1000, history=history or [], buy_limit=1000,
                      high_time=high_time, low_time=low_time)


def test_stale_price_skips_buy():
    import time
    conn = fresh()
    runs.start_run(conn, "alwaysbuy", budget_gp=10_000)
    old = int(time.time()) - 200_000   # ~2.3 days old, beyond 86400 default
    evaluate(conn, {1: _mkt(1, 100, 200, high_time=old, low_time=old)},
             now=0.0, loader=loader_stub)
    assert pos.list_positions(conn, state="proposed") == []


def test_fresh_price_allows_buy():
    import time
    conn = fresh()
    runs.start_run(conn, "alwaysbuy", budget_gp=10_000)
    now = int(time.time())
    evaluate(conn, {1: _mkt(1, 100, 200, high_time=now, low_time=now)},
             now=0.0, loader=loader_stub)
    assert len(pos.list_positions(conn, state="proposed")) == 1


def test_spike_price_skips_buy():
    conn = fresh()
    runs.start_run(conn, "alwaysbuy", budget_gp=10_000_000)
    hist = [{"avgLowPrice": 100, "avgHighPrice": 110} for _ in range(30)]
    # current low 1000 is 10x the ~100 median -> spike (default factor 5) -> skip
    evaluate(conn, {1: _mkt(1, 1000, 1100, history=hist)},
             now=0.0, loader=loader_stub)
    assert pos.list_positions(conn, state="proposed") == []


def test_none_price_does_not_crash_or_buy():
    conn = fresh()
    runs.start_run(conn, "alwaysbuy", budget_gp=10_000)
    # find_buys compares budget >= m.low; None low -> AlwaysBuy skips it, and the
    # engine's guard also drops it. Must not raise.
    evaluate(conn, {1: _mkt(1, None, None)}, now=0.0, loader=loader_stub)
    assert pos.list_positions(conn, state="proposed") == []


def test_buy_deduped_across_runs():
    conn = fresh()
    runs.start_run(conn, "alwaysbuy", budget_gp=10_000)
    runs.start_run(conn, "alwaysbuy", budget_gp=10_000)   # second auto/manual run
    evaluate(conn, {1: market(1, 100, 150)}, now=0.0, loader=loader_stub)
    # only one run gets the item; the other sees it already open and skips
    assert len(pos.list_positions(conn, state="proposed")) == 1


class BigQtyBuy:
    """Wants a large qty of every market item (engine must cap by buy limit)."""
    name = "bigqty"
    def __init__(self, **p): self.params = p
    def find_buys(self, markets, budget):
        return [BuySignal(item_id=m.item_id, price=m.low, qty=1000, reason="x")
                for m in markets]
    def should_sell(self, position, market):
        return SellDecision(sell=False, reason="")


def bigqty_loader(_dir):
    return {"bigqty": BigQtyBuy()}


def test_cumulative_4h_buy_limit_caps_qty():
    import time
    conn = fresh()
    rid = runs.start_run(conn, "bigqty", budget_gp=10_000_000)
    # already bought 8 of item 1 within the last 4h; buy_limit is 10
    pid = pos.create_proposed(conn, strategy="bigqty", item_id=1, item_name="i1",
                              buy_price=100, qty=8, run_id=rid)
    pos.accept(conn, pid)               # accepted_at = now, counts toward 4h limit
    # mark sold so it's not an open position (dedupe would otherwise block)
    pos.mark_filled(conn, pid); pos.start_selling(conn, pid); pos.mark_sold(conn, pid, 150)
    now = int(time.time())
    m = MarketData(item_id=1, name="i1", low=100, high=150, vol_1h=1000,
                   history=[], buy_limit=10, high_time=now, low_time=now)
    evaluate(conn, {1: m}, now=0.0, loader=bigqty_loader)
    prop = pos.list_positions(conn, state="proposed")
    assert len(prop) == 1 and prop[0]["qty"] == 2     # 10 limit - 8 recent = 2


def test_cumulative_4h_limit_blocks_when_exhausted():
    import time
    conn = fresh()
    rid = runs.start_run(conn, "bigqty", budget_gp=10_000_000)
    pid = pos.create_proposed(conn, strategy="bigqty", item_id=1, item_name="i1",
                              buy_price=100, qty=10, run_id=rid)
    pos.accept(conn, pid)
    pos.mark_filled(conn, pid); pos.start_selling(conn, pid); pos.mark_sold(conn, pid, 150)
    now = int(time.time())
    m = MarketData(item_id=1, name="i1", low=100, high=150, vol_1h=1000,
                   history=[], buy_limit=10, high_time=now, low_time=now)
    evaluate(conn, {1: m}, now=0.0, loader=bigqty_loader)
    assert pos.list_positions(conn, state="proposed") == []   # limit used up


def test_sell_uses_position_params_not_run_params():
    conn = fresh()
    # run carries a HIGH sell_at (would NOT sell); position carries a LOW one
    rid = runs.start_run(conn, "paramsell", budget_gp=10_000, params={"sell_at": 999999})
    pid = pos.create_proposed(conn, strategy="paramsell", item_id=1, item_name="i1",
                              buy_price=100, qty=1, run_id=rid, params={"sell_at": 100})
    pos.accept(conn, pid); pos.mark_filled(conn, pid)
    evaluate(conn, {1: market(1, 120, 150)}, now=0.0, loader=paramsell_loader)
    sigs = conn.execute("SELECT * FROM signals WHERE type='sell'").fetchall()
    assert len(sigs) == 1   # high 150 >= position's sell_at 100 -> sell, despite run's 999999
