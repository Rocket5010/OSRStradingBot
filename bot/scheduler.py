# bot/scheduler.py
"""Background poll+evaluate scheduler. Owns its own db connection."""

import threading
import time

from bot.poller import poll_once
from bot.engine_live import evaluate
from bot.strategies.loader import load_strategies


class PollScheduler:
    def __init__(self, conn, client, watchlist, interval_s=300,
                 timestep="24h", loader=load_strategies,
                 notifier=None, goal_interval_s=86400):
        self.conn = conn
        self.client = client
        self.watchlist = watchlist
        self.interval_s = interval_s
        self.timestep = timestep
        self.loader = loader
        from bot import notify as _notify
        self.notifier = notifier or _notify.notify
        self.goal_interval_s = goal_interval_s
        self._last_goal = None
        self._mapping = None
        self._history = None
        self._stop = threading.Event()
        self._thread = None

    def _ensure_context(self):
        from bot.market import HistoryCache
        if self._mapping is None:
            self._mapping = {str(m["id"]): m for m in self.client.mapping()}
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
                pass
            self._last_goal = now

        poll_once(self.client, self.conn)
        markets = build_market_data(self.conn, self._mapping, self._history,
                                    self.watchlist, now=now)
        market_map = {m.item_id: m for m in markets}

        webhook = db.get_config(self.conn, "notify_webhook")
        before_props = {p["id"] for p in pos.list_positions(self.conn, "proposed")}
        before_sells = {r["id"] for r in self.conn.execute(
            "SELECT id FROM signals WHERE type='sell'").fetchall()}

        evaluate(self.conn, market_map, now=now, loader=self.loader)

        if webhook:
            for p in pos.list_positions(self.conn, "proposed"):
                if p["id"] not in before_props:
                    self.notifier(webhook, notify_mod.format_buy(
                        p["item_name"], p["buy_price"], p["qty"], "signal"))
            for r in self.conn.execute(
                    "SELECT * FROM signals WHERE type='sell'").fetchall():
                if r["id"] not in before_sells:
                    self.notifier(webhook, notify_mod.format_sell(
                        r["item_id"], r["price"], r["reason"] or ""))

    def _loop(self):
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                pass  # a poll failure must not kill the loop
            self._stop.wait(self.interval_s)

    def start(self):
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
