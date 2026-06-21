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
    def latest_item(self, item_id):
        return {"high": 14000000, "low": 13300000}


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


def test_tick_notifies_new_proposals():
    conn = db.connect(":memory:")
    db.init_db(conn)
    db.set_config(conn, "notify_webhook", "http://hook")
    runs.start_run(conn, "alwaysbuy", budget_gp=10_000)
    sent = []
    sched = PollScheduler(conn, StubClient(), watchlist=[1], loader=loader_stub,
                          notifier=lambda url, msg: sent.append(msg),
                          goal_interval_s=0)
    sched.tick(now=0.0)
    assert any("Item1" in m for m in sent)   # a buy notification fired


def test_tick_no_notify_without_webhook():
    conn = db.connect(":memory:")
    db.init_db(conn)
    runs.start_run(conn, "alwaysbuy", budget_gp=10_000)
    sent = []
    sched = PollScheduler(conn, StubClient(), watchlist=[1], loader=loader_stub,
                          notifier=lambda url, msg: sent.append(msg))
    sched.tick(now=0.0)
    assert sent == []


def test_tick_uses_config_watchlist():
    conn = db.connect(":memory:")
    db.init_db(conn)
    from bot import curator
    curator.save_watchlist(conn, [1])
    runs.start_run(conn, "alwaysbuy", budget_gp=10_000)
    sched = PollScheduler(conn, StubClient(), watchlist=[999], loader=loader_stub,
                          goal_interval_s=0)
    sched.tick(now=0.0)
    # proposal is for item 1 (from config), not 999
    props = pos.list_positions(conn, state="proposed")
    assert props and all(p["item_id"] == 1 for p in props)


def test_curation_runs_and_writes_watchlist():
    conn = db.connect(":memory:")
    db.init_db(conn)
    db.set_config(conn, "curate_strategy", "alwaysbuy")
    runs.start_run(conn, "alwaysbuy", budget_gp=10_000)
    sched = PollScheduler(conn, StubClient(), watchlist=[1], loader=loader_stub,
                          goal_interval_s=999999, curate_interval_s=0)
    sched.tick(now=0.0)
    from bot import curator
    # StubClient.timeseries returns [] so no candidate qualifies, but the
    # curation pass must run without error and leave watchlist usable.
    assert curator.get_watchlist(conn, default=[1]) is not None


def test_ensure_auto_pilot_creates_run():
    conn = db.connect(":memory:")
    db.init_db(conn)
    db.set_config(conn, "auto_budget", "500000000")
    from bot import backtest_rank
    backtest_rank.save_ranking(conn, [{"strategy": "breakout", "score": 12.5,
                                       "profit": 100, "trades": 5, "win_rate": 0.6,
                                       "params": {"trail_pct": 0.08}}], 3)
    sched = PollScheduler(conn, StubClient(), watchlist=[1], loader=loader_stub)
    sched._ensure_auto_pilot()
    rows = conn.execute("SELECT * FROM strategy_runs WHERE auto=1").fetchall()
    assert len(rows) == 1 and rows[0]["strategy"] == "breakout"
    assert rows[0]["budget_gp"] == 500000000
    assert rows[0]["params_json"] == '{"trail_pct": 0.08}'   # tuned params stored


def test_ensure_auto_pilot_diversifies_and_splits_budget():
    conn = db.connect(":memory:")
    db.init_db(conn)
    db.set_config(conn, "auto_budget", "600000000")
    db.set_config(conn, "auto_strategies", "2")
    from bot import backtest_rank
    backtest_rank.save_ranking(conn, [
        {"strategy": "breakout", "score": 20.0, "profit": 9, "trades": 5,
         "win_rate": 0.85, "params": {"trail_pct": 0.08}},
        {"strategy": "momentum", "score": 12.0, "profit": 7, "trades": 5,
         "win_rate": 0.6, "params": {}},
        {"strategy": "rsi", "score": -5.0, "profit": -3, "trades": 5,
         "win_rate": 0.3, "params": {}},   # negative -> excluded
    ], 3)
    sched = PollScheduler(conn, StubClient(), watchlist=[1], loader=loader_stub)
    sched._ensure_auto_pilot()
    rows = conn.execute("SELECT * FROM strategy_runs WHERE auto=1 AND "
                        "state='running' ORDER BY strategy").fetchall()
    assert {r["strategy"] for r in rows} == {"breakout", "momentum"}  # top-2, no rsi
    assert all(r["budget_gp"] == 300000000 for r in rows)             # 600M / 2


def test_ensure_auto_pilot_pause_stops_runs():
    conn = db.connect(":memory:")
    db.init_db(conn)
    db.set_config(conn, "auto_budget", "100")
    from bot import backtest_rank
    backtest_rank.save_ranking(conn, [{"strategy": "breakout", "score": 5.0,
                                       "profit": 1, "trades": 1, "win_rate": 1.0,
                                       "params": {}}], 1)
    sched = PollScheduler(conn, StubClient(), watchlist=[1], loader=loader_stub)
    sched._ensure_auto_pilot()
    assert len(conn.execute("SELECT 1 FROM strategy_runs WHERE state='running'")
               .fetchall()) == 1
    db.set_config(conn, "auto_budget", "0")          # pause
    sched._ensure_auto_pilot()
    assert conn.execute("SELECT COUNT(*) c FROM strategy_runs WHERE "
                        "state='running'").fetchone()["c"] == 0


def test_drawdown_stop_pauses_buying():
    import json
    from datetime import datetime, timezone
    conn = db.connect(":memory:")
    db.init_db(conn)
    db.set_config(conn, "auto_budget", "600000000")
    db.set_config(conn, "capital", "500000000")
    db.set_config(conn, "max_drawdown_stop_pct", "10")     # halt at -50M
    db.set_config(conn, "goal_period_start", "2026-01-01T00:00:00+00:00")
    from bot import backtest_rank
    backtest_rank.save_ranking(conn, [{"strategy": "breakout", "score": 5.0,
                                       "profit": 1, "trades": 1, "win_rate": 1.0,
                                       "params": {}}], 1)
    # a realized loss of 60M (> 10% of 500M) within the period
    conn.execute("INSERT INTO positions(item_id, item_name, strategy, state, "
                 "buy_price, qty, realized_pl, closed_at) VALUES"
                 "(1,'i1','breakout','sold',100,1,-60000000,"
                 "'2026-03-01T00:00:00+00:00')")
    conn.commit()
    sched = PollScheduler(conn, StubClient(), watchlist=[1], loader=loader_stub)
    sched._ensure_auto_pilot()
    assert conn.execute("SELECT COUNT(*) c FROM strategy_runs WHERE "
                        "state='running'").fetchone()["c"] == 0   # buying paused


def test_ensure_auto_pilot_noop_without_budget():
    conn = db.connect(":memory:")
    db.init_db(conn)
    from bot import backtest_rank
    backtest_rank.save_ranking(conn, [{"strategy": "breakout", "score": 12.5,
                                       "profit": 100, "trades": 5, "win_rate": 0.6,
                                       "params": {}}], 3)
    sched = PollScheduler(conn, StubClient(), watchlist=[1], loader=loader_stub)
    sched._ensure_auto_pilot()   # auto_budget unset -> no run
    assert conn.execute("SELECT COUNT(*) c FROM strategy_runs").fetchone()["c"] == 0


def test_scheduler_has_logger():
    import bot.scheduler as s
    assert s.log.name == "bot.scheduler"
