# bot/main.py
"""Entry point: open db, start the poll scheduler on its own connection, and
serve the FastAPI app. The API and the scheduler use SEPARATE connections."""

import os
import threading

import uvicorn

from bot import db
from bot.api_client import WikiClient
from bot.scheduler import PollScheduler
from bot.web import create_app

_curate_lock = threading.Lock()

DB_PATH = os.environ.get("OSRS_BOT_DB", "osrs_bot.db")
USER_AGENT = os.environ.get(
    "OSRS_BOT_UA", "osrs-flip-bot/1.0 (contact: set OSRS_BOT_UA)")
# Bind address: default private (127.0.0.1). Set OSRS_BOT_HOST=0.0.0.0 to reach
# the dashboard from another machine (e.g. a local practice VM). Do NOT expose
# 0.0.0.0 on a public server without a firewall/auth — use an SSH tunnel there.
HOST = os.environ.get("OSRS_BOT_HOST", "127.0.0.1")
PORT = int(os.environ.get("OSRS_BOT_PORT", "8000"))
# Default watchlist; replace/extend via config later.
WATCHLIST = [4151, 11802, 11832, 4712, 11785]


def build():
    api_conn = db.connect(DB_PATH)
    db.init_db(api_conn)
    client = WikiClient(user_agent=USER_AGENT)

    sched_conn = db.connect(DB_PATH)   # separate connection for the thread
    # scheduler also refreshes the bond goal daily and sends webhook
    # notifications when config key 'notify_webhook' is set.
    # WATCHLIST is the fallback until the curator populates config 'watchlist'.
    scheduler = PollScheduler(sched_conn, client, watchlist=WATCHLIST)

    def curate_runner():
        if not _curate_lock.acquire(blocking=False):
            return  # a curation is already in progress
        def job():
            c = db.connect(DB_PATH)
            try:
                db.init_db(c)
                from bot.curate_now import run
                run(c, client)   # shared thread-safe client keeps the rate limit global
            finally:
                c.close()
                _curate_lock.release()
        threading.Thread(target=job, daemon=True).start()

    app = create_app(api_conn, curate_runner=curate_runner)
    return app, scheduler


def main():
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app, scheduler = build()
    scheduler.start()
    try:
        uvicorn.run(app, host=HOST, port=PORT)
    finally:
        scheduler.stop()


if __name__ == "__main__":
    main()
