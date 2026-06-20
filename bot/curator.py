# bot/curator.py
"""Periodically screen the market and backtest candidates to build the
investing watchlist. Reuses the Phase 3 backtest engine."""

import logging

from bot import db
from bot.backtest.engine import run_backtest

log = logging.getLogger("bot.curator")


def _top_by(conn, order_expr, where, params, cap):
    sql = (f"SELECT item_id FROM price_cache WHERE {where} "
           f"ORDER BY {order_expr} DESC LIMIT ?")
    return [r["item_id"] for r in conn.execute(sql, [*params, cap]).fetchall()]


def screen_candidates(conn, min_vol=100, min_price=1, max_price=None, cap=200):
    """Liquid items from price_cache, top `cap` by 1h volume."""
    where = "vol_1h >= ? AND low >= ? AND low > 0"
    params = [min_vol, min_price]
    if max_price is not None:
        where += " AND high <= ?"
        params.append(max_price)
    return _top_by(conn, "vol_1h", where, params, cap)


def screen_two_bucket(conn, liquid_min_vol=100, liquid_cap=150,
                      value_min_vol=10, value_min_price=100_000, value_cap=100):
    """Two opportunity buckets merged:
      - liquid: high 1h volume (cheap, fast-flipping items) — the old behaviour.
      - value: expensive items (>= value_min_price) at a much lower volume floor,
        ranked by absolute spread * sqrt(volume) so a real margin can outweigh
        thin volume. Without this bucket the volume-DESC sort buries every
        expensive high-margin item (whips, armour, 3rd-age) under cheap runes.
    Returns a de-duplicated list. The backtest is still the final judge — items
    that can't actually be sold score badly and get dropped."""
    liquid = screen_candidates(conn, min_vol=liquid_min_vol, cap=liquid_cap)
    # Rank the value bucket by spread * volume: a real gp spread can outweigh
    # thin volume, but volume still breaks ties so totally illiquid junk sinks.
    # The price floor already excludes cheap items, so volume can't dominate.
    value = _top_by(
        conn,
        "(high - low) * vol_1h",
        "vol_1h >= ? AND low >= ? AND high > low AND low > 0",
        [value_min_vol, value_min_price],
        value_cap)
    seen, merged = set(), []
    for item_id in [*liquid, *value]:
        if item_id not in seen:
            seen.add(item_id)
            merged.append(item_id)
    return merged


def curate(conn, client, strategy_factory, candidate_ids, budget,
           top_n=50, timestep="24h", min_candles=30, max_drawdown=0.4,
           max_hold_steps=30, on_progress=None):
    """Backtest each candidate; return the top_n item ids ranked by risk-adjusted
    gp/day (risk_score), not raw profit, so the watchlist favours items that earn
    steadily within tolerable drawdown. strategy_factory is a zero-arg callable
    returning a fresh Strategy."""
    log.info("curation: backtesting %d candidates", len(candidate_ids))
    scored = []
    total = len(candidate_ids)
    for i, item_id in enumerate(candidate_ids, start=1):
        candles = client.timeseries(item_id, timestep)
        if len(candles) >= min_candles:
            result = run_backtest(strategy_factory(), candles, budget,
                                  item_id=item_id, max_hold_steps=max_hold_steps)
            if (result.n_trades > 0 and result.max_drawdown <= max_drawdown
                    and result.total_profit > 0):
                scored.append((item_id, result.risk_score, result.hit_rate))
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
