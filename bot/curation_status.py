# bot/curation_status.py
"""Thread-safe, in-memory status of the watchlist curation job so the API can
report live progress to the dashboard."""

import threading
from datetime import datetime, timezone


class CurationStatus:
    def __init__(self):
        self._lock = threading.Lock()
        self.running = False
        self.done = 0
        self.total = 0
        self.last_count = None
        self.last_finished = None
        self.last_error = None

    def start(self, total=0):
        with self._lock:
            self.running = True
            self.done = 0
            self.total = total
            self.last_error = None

    def progress(self, done, total):
        with self._lock:
            self.done = done
            self.total = total

    def _stamp(self):
        return datetime.now(timezone.utc).isoformat()

    def finish(self, count):
        with self._lock:
            self.running = False
            self.last_count = count
            self.last_finished = self._stamp()

    def fail(self, err):
        with self._lock:
            self.running = False
            self.last_error = str(err)
            self.last_finished = self._stamp()

    def snapshot(self):
        with self._lock:
            return {
                "running": self.running,
                "done": self.done,
                "total": self.total,
                "last_count": self.last_count,
                "last_finished": self.last_finished,
                "last_error": self.last_error,
            }
