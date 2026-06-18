# bot/main.py
"""Entry point: open db, start the poll scheduler on its own connection, and
serve the FastAPI app. The API and the scheduler use SEPARATE connections."""

import os

import uvicorn

from bot import db
from bot.api_client import WikiClient
from bot.scheduler import PollScheduler
from bot.web import create_app

DB_PATH = os.environ.get("OSRS_BOT_DB", "osrs_bot.db")
USER_AGENT = os.environ.get(
    "OSRS_BOT_UA", "osrs-flip-bot/1.0 (contact: set OSRS_BOT_UA)")
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

    app = create_app(api_conn)
    return app, scheduler


def main():
    app, scheduler = build()
    scheduler.start()
    try:
        uvicorn.run(app, host="127.0.0.1", port=8000)
    finally:
        scheduler.stop()


if __name__ == "__main__":
    main()
