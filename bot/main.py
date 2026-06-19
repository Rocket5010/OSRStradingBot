# bot/main.py
"""Entry point: open db, start the poll scheduler on its own connection, and
serve the FastAPI app. The API and the scheduler use SEPARATE connections."""

import os
import threading

import uvicorn

from bot import db
from bot.api_client import WikiClient
from bot.curation_status import CurationStatus
from bot.scheduler import PollScheduler
from bot.web import create_app

_curate_lock = threading.Lock()
_backtest_lock = threading.Lock()

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
    curation_status = CurationStatus()
    backtest_status = CurationStatus()

    sched_conn = db.connect(DB_PATH)   # separate connection for the thread
    # scheduler also refreshes the bond goal daily and sends webhook
    # notifications when config key 'notify_webhook' is set.
    # WATCHLIST is the fallback until the curator populates config 'watchlist'.
    scheduler = PollScheduler(sched_conn, client, watchlist=WATCHLIST,
                              db_path=DB_PATH)

    def curate_runner():
        if not _curate_lock.acquire(blocking=False):
            return  # a curation is already in progress
        def job():
            c = db.connect(DB_PATH)
            curation_status.start()
            try:
                db.init_db(c)
                from bot.curate_now import run
                picks = run(c, client, on_progress=curation_status.progress)
                curation_status.finish(len(picks))
            except Exception as e:
                curation_status.fail(e)
            finally:
                c.close()
                _curate_lock.release()
        threading.Thread(target=job, daemon=True).start()

    def backtest_runner():
        if not _backtest_lock.acquire(blocking=False):
            return
        def job():
            c = db.connect(DB_PATH)
            backtest_status.start()
            try:
                db.init_db(c)
                from bot.curator import get_watchlist
                from bot import backtest_rank
                items = get_watchlist(c) or backtest_rank.DEFAULT_BASKET
                ranking = backtest_rank.rank_over_items(
                    client, items, on_progress=backtest_status.progress)
                backtest_rank.save_ranking(c, ranking, len(items))
                backtest_status.finish(len(ranking))
            except Exception as e:
                backtest_status.fail(e)
            finally:
                c.close()
                _backtest_lock.release()
        threading.Thread(target=job, daemon=True).start()

    app = create_app(api_conn, curate_runner=curate_runner, curation_status=curation_status, backtest_runner=backtest_runner, backtest_status=backtest_status)
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
