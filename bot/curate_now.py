# bot/curate_now.py
"""One-shot watchlist curation: poll prices, screen candidates, backtest-rank,
and save the winners to the 'watchlist' config. Run: python -m bot.curate_now"""

import os

from bot import db, curator
from bot.api_client import WikiClient
from bot.poller import poll_once
from bot.strategies.loader import load_strategies


def run(conn, client, strategies_dir=None, cap=None, budget=None, min_candles=30):
    """Poll, screen, curate, save. Returns the chosen item ids."""
    strategies_dir = strategies_dir or os.path.join(
        os.path.dirname(__file__), "strategies")
    strat_name = db.get_config(conn, "curate_strategy") or "mean_reversion"
    found = load_strategies(strategies_dir)
    if strat_name not in found:
        raise SystemExit(f"unknown curate_strategy '{strat_name}'")
    factory = type(found[strat_name])
    poll_once(client, conn)
    cap = cap or int(os.environ.get("CURATE_CAP", "100"))
    budget = budget or int(db.get_config(conn, "curate_budget") or "10000000")
    candidates = curator.screen_candidates(conn, cap=cap)
    picks = curator.curate(conn, client, factory, candidates, budget,
                           min_candles=min_candles)
    curator.save_watchlist(conn, picks)
    return picks


def main():
    db_path = os.environ.get("OSRS_BOT_DB", "osrs_bot.db")
    ua = os.environ.get("OSRS_BOT_UA", "osrs-flip-bot/1.0 (set OSRS_BOT_UA)")
    conn = db.connect(db_path)
    db.init_db(conn)
    client = WikiClient(user_agent=ua)
    print("Polling prices and curating (this can take a few minutes)...")
    picks = run(conn, client)
    print(f"Watchlist set to {len(picks)} items: {picks}")


if __name__ == "__main__":
    main()
