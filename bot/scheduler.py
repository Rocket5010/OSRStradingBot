# bot/scheduler.py
"""Background poll+evaluate scheduler. Owns its own db connection."""

import logging
import threading
import time

from bot.poller import poll_once

log = logging.getLogger("bot.scheduler")
from bot.engine_live import evaluate
from bot.strategies.loader import load_strategies


class PollScheduler:
    def __init__(self, conn, client, watchlist, interval_s=300,
                 timestep="24h", loader=load_strategies,
                 notifier=None, goal_interval_s=86400,
                 curate_interval_s=604800, backtest_interval_s=604800,
                 db_path=None):
        self.conn = conn
        self.client = client
        self.watchlist = watchlist
        self.interval_s = interval_s
        self.timestep = timestep
        self.loader = loader
        from bot import notify as _notify
        self.notifier = notifier or _notify.notify
        self.goal_interval_s = goal_interval_s
        self.curate_interval_s = curate_interval_s
        self.backtest_interval_s = backtest_interval_s
        # If set, periodic curation runs in its OWN thread + connection so a slow
        # network curation can't stall the poll loop. Without it (tests), curation
        # runs inline on self.conn.
        self.db_path = db_path
        self._curate_lock = threading.Lock()
        self._backtest_lock = threading.Lock()
        self.default_watchlist = watchlist
        self._last_curate = None
        self._last_goal = None
        self._last_backtest = None
        self._mapping = None
        self._history = None
        self._stop = threading.Event()
        self._thread = None

    def _ensure_context(self):
        from bot.market import HistoryCache
        if self._mapping is None:
            self._mapping = {str(m["id"]): m for m in self.client.mapping()}
            from bot import db as _db
            _db.save_item_names(self.conn, self._mapping)
        if self._history is None:
            self._history = HistoryCache(self.client, timestep=self.timestep)

    def tick(self, now=None):
        import time as _time
        from bot import db, positions as pos, goal as goal_mod, notify as notify_mod
        from bot.market import build_market_data
        now = _time.monotonic() if now is None else now
        self._ensure_context()

        # bond goal refresh (throttled)
        if self._last_goal is None or (now - self._last_goal) >= self.goal_interval_s:
            try:
                goal_mod.refresh_bond_goal(self.conn, self.client)
            except Exception:
                log.exception("bond goal refresh failed")
            self._last_goal = now

        poll_once(self.client, self.conn)

        # periodic watchlist curation (slow cadence)
        if self._last_curate is None or (now - self._last_curate) >= self.curate_interval_s:
            self._start_curation()
            self._last_curate = now

        # weekly strategy-ranking refresh (slow cadence)
        if self._last_backtest is None or (now - self._last_backtest) >= self.backtest_interval_s:
            self._start_backtest()
            self._last_backtest = now
        # auto-pilot: keep the auto-run pointed at the current best strategy
        self._ensure_auto_pilot()

        from bot.curator import get_watchlist
        watch = get_watchlist(self.conn, default=self.default_watchlist)
        markets = build_market_data(self.conn, self._mapping, self._history,
                                    watch, now=now)
        market_map = {m.item_id: m for m in markets}

        webhook = db.get_config(self.conn, "notify_webhook")
        before_props = {p["id"] for p in pos.list_positions(self.conn, "proposed")}
        before_sells = {r["id"] for r in self.conn.execute(
            "SELECT id FROM signals WHERE type='sell'").fetchall()}

        evaluate(self.conn, market_map, now=now, loader=self.loader)

        if webhook:
            for p in pos.list_positions(self.conn, "proposed"):
                if p["id"] not in before_props:
                    try:
                        self.notifier(webhook, notify_mod.format_buy(
                            p["item_name"], p["buy_price"], p["qty"], "signal"))
                    except Exception:
                        log.warning("notification failed", exc_info=True)
            for r in self.conn.execute(
                    "SELECT * FROM signals WHERE type='sell'").fetchall():
                if r["id"] not in before_sells:
                    meta = self._mapping.get(str(r["item_id"]), {})
                    name = meta.get("name", str(r["item_id"]))
                    try:
                        self.notifier(webhook, notify_mod.format_sell(
                            name, r["price"], r["reason"] or ""))
                    except Exception:
                        log.warning("notification failed", exc_info=True)

    def _ensure_auto_pilot(self):
        """Diversified auto-pilot: split the auto-budget across the top-N
        positively-scored strategies. Spreading capital lowers the damage if the
        single best strategy stops working — better odds, less variance. N comes
        from the `auto_strategies` config (default 3)."""
        from bot import db, backtest_rank
        from bot import runs as runs_mod
        auto_budget = int(db.get_config(self.conn, "auto_budget") or "0")
        if auto_budget <= 0:
            runs_mod.ensure_auto_runs(self.conn, [])   # paused -> stop buying
            return
        # portfolio kill-switch: if the period's realized loss exceeds the
        # drawdown-stop fraction of capital, stop opening new positions. Held
        # positions keep selling (the sell loop is independent of auto-runs).
        if self._drawdown_breached(db):
            runs_mod.ensure_auto_runs(self.conn, [])
            return
        n = max(1, int(db.get_config(self.conn, "auto_strategies") or "3"))
        ranking = backtest_rank.get_ranking(self.conn).get("ranking") or []
        winners = [r for r in ranking if r["score"] > 0][:n]
        if not winners:
            runs_mod.ensure_auto_runs(self.conn, [])
            return
        budget_each = auto_budget // len(winners)
        specs = [(w["strategy"], budget_each, w.get("params") or {})
                 for w in winners]
        runs_mod.ensure_auto_runs(self.conn, specs)

    def _drawdown_breached(self, db):
        """True if the period's realized P/L is a loss bigger than
        max_drawdown_stop_pct of capital (config; 0 = off)."""
        pct = float(db.get_config(self.conn, "max_drawdown_stop_pct") or "0")
        if pct <= 0:
            return False
        capital = int(db.get_config(self.conn, "capital") or "0")
        if capital <= 0:
            return False
        period_start = db.get_config(self.conn, "goal_period_start")
        if not period_start:
            return False
        row = self.conn.execute(
            "SELECT COALESCE(SUM(realized_pl), 0) AS s FROM positions "
            "WHERE state='sold' AND closed_at >= ?", (period_start,)).fetchone()
        return row["s"] < -(pct / 100.0) * capital

    def _start_backtest(self):
        """Refresh the strategy ranking. Threaded with its own connection when
        db_path is set; inline on self.conn otherwise (tests)."""
        if not self._backtest_lock.acquire(blocking=False):
            return

        def _do(conn):
            from bot import backtest_rank
            from bot.curator import get_watchlist
            items = get_watchlist(conn) or backtest_rank.DEFAULT_BASKET
            ranking = backtest_rank.rank_over_items(self.client, items, tune=True)
            backtest_rank.save_ranking(conn, ranking, len(items))

        if self.db_path is None:
            try:
                _do(self.conn)
            except Exception:
                log.exception("auto backtest failed")
            finally:
                self._backtest_lock.release()
            return

        def job():
            from bot import db as _db
            c = None
            try:
                c = _db.connect(self.db_path)
                _db.init_db(c)
                _do(c)
            except Exception:
                log.exception("auto backtest failed")
            finally:
                if c is not None:
                    c.close()
                self._backtest_lock.release()

        threading.Thread(target=job, daemon=True).start()

    def _start_curation(self):
        """Run a curation pass. Threaded with its own connection when db_path is
        set; inline on self.conn otherwise (tests). Never overlaps itself."""
        if not self._curate_lock.acquire(blocking=False):
            return  # a curation is already running
        if self.db_path is None:
            try:
                self._curate(self.conn)
            except Exception:
                log.exception("curation failed")
            finally:
                self._curate_lock.release()
            return

        def job():
            from bot import db as _db
            c = None
            try:
                c = _db.connect(self.db_path)
                _db.init_db(c)
                self._curate(c)
            except Exception:
                log.exception("curation failed")
            finally:
                if c is not None:
                    c.close()
                self._curate_lock.release()

        threading.Thread(target=job, daemon=True).start()

    def _curate(self, conn):
        from bot import db, curator
        strat_name = db.get_config(conn, "curate_strategy") or "mean_reversion"
        found = self.loader(self._strategies_dir())
        if strat_name not in found:
            return
        factory = type(found[strat_name])
        candidates = curator.screen_two_bucket(conn)
        budget = int(db.get_config(conn, "curate_budget") or "10000000")
        picks = curator.curate(conn, self.client, factory, candidates, budget)
        if picks:
            curator.save_watchlist(conn, picks)

    def _strategies_dir(self):
        import os
        return os.path.join(os.path.dirname(__file__), "strategies")

    def _loop(self):
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                log.exception("scheduler tick failed")  # keep the loop alive
            self._stop.wait(self.interval_s)

    def start(self):
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
