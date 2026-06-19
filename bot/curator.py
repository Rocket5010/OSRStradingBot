# bot/curator.py
"""Periodically screen the market and backtest candidates to build the
investing watchlist. Reuses the Phase 3 backtest engine."""

import logging

from bot import db
from bot.backtest.engine import run_backtest

log = logging.getLogger("bot.curator")


def screen_candidates(conn, min_vol=100, min_price=1, max_price=None, cap=200):
    """Liquid items from price_cache, top `cap` by 1h volume."""
    sql = ("SELECT item_id FROM price_cache "
           "WHERE vol_1h >= ? AND low >= ? AND low > 0")
    params = [min_vol, min_price]
    if max_price is not None:
        sql += " AND high <= ?"
        params.append(max_price)
    sql += " ORDER BY vol_1h DESC LIMIT ?"
    params.append(cap)
    return [r["item_id"] for r in conn.execute(sql, params).fetchall()]


def curate(conn, client, strategy_factory, candidate_ids, budget,
           top_n=50, timestep="24h", min_candles=30, max_drawdown=0.4,
           on_progress=None):
    """Backtest each candidate; return the top_n item ids by profit.
    strategy_factory is a zero-arg callable returning a fresh Strategy."""
    log.info("curation: backtesting %d candidates", len(candidate_ids))
    scored = []
    total = len(candidate_ids)
    for i, item_id in enumerate(candidate_ids, start=1):
        candles = client.timeseries(item_id, timestep)
        if len(candles) >= min_candles:
            result = run_backtest(strategy_factory(), candles, budget, item_id=item_id)
            if (result.n_trades > 0 and result.max_drawdown <= max_drawdown
                    and result.total_profit > 0):
                scored.append((item_id, result.total_profit, result.hit_rate))
        if on_progress is not None:
            on_progress(i, total)
    scored.sort(key=lambda x: (x[1], x[2]), reverse=True)
    picks = [item_id for item_id, _, _ in scored[:top_n]]
    log.info("curation: done, picked %d items", len(picks))
    return picks


def save_watchlist(conn, item_ids):
    db.set_config(conn, "watchlist", ",".join(str(i) for i in item_ids))


def get_watchlist(conn, default=None):
    try:
        raw = db.get_config(conn, "watchlist")
    except Exception:
        raw = None
    if not raw:
        return list(default) if default else []
    out = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            out.append(int(token))
        except ValueError:
            continue
    return out
