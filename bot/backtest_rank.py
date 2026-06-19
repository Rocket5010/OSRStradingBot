# bot/backtest_rank.py
"""Rank every strategy over a basket of items by aggregated backtest profit.
Lets the dashboard answer 'which strategy worked best historically'."""

import json
import os
from datetime import datetime, timezone

from bot import db
from bot.backtest.engine import run_backtest
from bot.strategies.loader import load_strategies

# A spread of liquid items used when the watchlist is empty.
DEFAULT_BASKET = [4151, 11802, 1515, 561, 565, 4587, 1127, 11212, 1392, 2, 11785, 12934]


def rank_over_items(client, item_ids, budget=10_000_000, timestep="24h",
                    strategies_dir=None, min_candles=30, on_progress=None):
    """Backtest each strategy over each item; aggregate profit/trades/wins and
    return a list of {strategy, profit, trades, win_rate} sorted by profit."""
    strategies_dir = strategies_dir or os.path.join(
        os.path.dirname(__file__), "strategies")
    strats = load_strategies(strategies_dir)
    agg = {name: {"profit": 0, "trades": 0, "wins": 0} for name in strats}
    total = len(item_ids)
    for i, item_id in enumerate(item_ids, start=1):
        candles = client.timeseries(item_id, timestep)
        if len(candles) >= min_candles:
            for name, proto in strats.items():
                r = run_backtest(type(proto)(), candles, budget, item_id=item_id)
                agg[name]["profit"] += r.total_profit
                agg[name]["trades"] += r.n_trades
                agg[name]["wins"] += sum(1 for t in r.trades if t["pl"] > 0)
        if on_progress is not None:
            on_progress(i, total)
    ranked = sorted(agg.items(), key=lambda kv: kv[1]["profit"], reverse=True)
    return [{"strategy": n, "profit": a["profit"], "trades": a["trades"],
             "win_rate": (a["wins"] / a["trades"]) if a["trades"] else 0.0}
            for n, a in ranked]


def save_ranking(conn, ranking, n_items):
    db.set_config(conn, "backtest_result", json.dumps({
        "ranking": ranking,
        "n_items": n_items,
        "finished": datetime.now(timezone.utc).isoformat(),
    }))


def get_ranking(conn):
    raw = db.get_config(conn, "backtest_result")
    if not raw:
        return {"ranking": [], "n_items": 0, "finished": None}
    return json.loads(raw)
