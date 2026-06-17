# bot/scheduler.py
"""Background poll+evaluate scheduler. Owns its own db connection."""

import threading
import time

from bot.poller import poll_once
from bot.engine_live import evaluate
from bot.strategies.loader import load_strategies


class PollScheduler:
    def __init__(self, conn, client, watchlist, interval_s=300,
                 timestep="24h", loader=load_strategies):
        self.conn = conn
        self.client = client
        self.watchlist = watchlist
        self.interval_s = interval_s
        self.timestep = timestep
        self.loader = loader
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
        now = time.monotonic() if now is None else now
        self._ensure_context()
        poll_once(self.client, self.conn)
        from bot.market import build_market_data
        markets = build_market_data(self.conn, self._mapping, self._history,
                                    self.watchlist, now=now)
        evaluate(self.conn, {m.item_id: m for m in markets}, now=now,
                 loader=self.loader)

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
