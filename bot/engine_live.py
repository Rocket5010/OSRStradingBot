# bot/engine_live.py
"""Live decision pass: turn running strategies + market data into proposed
positions and sell recommendations."""

import json
import os
from datetime import datetime, timezone, timedelta

from bot import runs as runs_mod
from bot import positions as pos_mod
from bot.market import position_view
from bot.strategies.loader import load_strategies
from bot.tax import ge_tax

_OPEN_STATES = ("proposed", "accepted", "filled", "selling")
_STRATEGIES_DIR = os.path.join(os.path.dirname(__file__), "strategies")
_strategy_cache = {}


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _make_strategy(name, params, loader):
    protos = _strategy_cache.get(loader)
    if protos is None:
        protos = loader(_STRATEGIES_DIR)
        _strategy_cache[loader] = protos
    proto = protos.get(name)
    if proto is None:
        return None
    # rebuild with the run's params if the class supports it
    try:
        return type(proto)(**params)
    except TypeError:
        return proto


def _has_open_position(conn, item_id):
    """True if ANY run already holds an open position in this item. Checked
    across runs (not per run) so diversified auto-runs don't pile multiple
    strategies into the same item and blow the shared 4h buy limit."""
    row = conn.execute(
        "SELECT 1 FROM positions WHERE item_id=? "
        f"AND state IN ({','.join('?' * len(_OPEN_STATES))}) LIMIT 1",
        (item_id, *_OPEN_STATES)).fetchone()
    return row is not None


_BUY_WINDOW_S = 4 * 3600  # GE buy limits reset every 4 hours


def _recent_bought_qty(conn, item_id, now_dt):
    """Units of an item bought within the last 4h (across all runs). Counts every
    position accepted in the window that wasn't withdrawn before buying, so the
    cumulative GE 4h limit is respected even across sequential buy/sell/buy."""
    cutoff = (now_dt - timedelta(seconds=_BUY_WINDOW_S)).isoformat()
    row = conn.execute(
        "SELECT COALESCE(SUM(qty), 0) AS s FROM positions "
        "WHERE item_id=? AND accepted_at IS NOT NULL AND accepted_at >= ? "
        "AND state IN ('accepted','filled','selling','sold')",
        (item_id, cutoff)).fetchone()
    return row["s"] or 0


def _price_age_s(m, epoch_now):
    """Seconds since the item last traded (max of high/low time), or None if the
    API gave no timestamps."""
    times = [t for t in (m.high_time, m.low_time) if t]
    if not times:
        return None
    return epoch_now - max(times)


def _median(values):
    s = sorted(values)
    n = len(s)
    if n == 0:
        return None
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def _is_spike(m, spike_factor):
    """True if the current buy price is more than spike_factor times the median
    recent low — a likely fat-finger or pump we shouldn't chase."""
    if spike_factor <= 0 or not m.history:
        return False
    lows = [c.get("avgLowPrice") for c in m.history if c.get("avgLowPrice")]
    med = _median(lows[-30:])
    return med is not None and med > 0 and m.low > med * spike_factor


def evaluate(conn, markets, now, loader=load_strategies):
    """markets: {item_id: MarketData}. Creates buy proposals for running runs
    (within available budget) and sell-recommendation signals for filled
    positions (one per position)."""
    import time as _time
    # Drop unusable markets up front so no strategy or tax call ever sees a None
    # or crossed price (build_market_data already filters live, this guards the
    # engine itself / direct callers).
    markets = {k: m for k, m in markets.items()
               if m is not None and m.low and m.high and m.high >= m.low}
    market_list = list(markets.values())

    from bot import db as _dbmod
    min_margin = int(_dbmod.get_config(conn, "min_margin_gp") or "0")
    # 0 = off. Default 24h: even thin value items shouldn't be acted on if their
    # last trade is older than this (the price is a guess, not a market).
    max_age = int(_dbmod.get_config(conn, "max_price_age_s") or "86400")
    spike_factor = float(_dbmod.get_config(conn, "spike_factor") or "5")
    epoch_now = _time.time()
    now_dt = datetime.now(timezone.utc)

    # --- buys, per running run ---
    for run in runs_mod.list_runs(conn, state="running"):
        params = json.loads(run["params_json"] or "{}")
        strat = _make_strategy(run["strategy"], params, loader)
        if strat is None:
            continue
        # available budget minus capital already tied up in this run's open
        # proposals (accepted+ is already reflected in spent_gp/available).
        proposed_cost = conn.execute(
            "SELECT COALESCE(SUM(buy_price * qty), 0) AS s FROM positions "
            "WHERE run_id=? AND state='proposed'", (run["id"],)).fetchone()["s"]
        budget = runs_mod.available(conn, run["id"]) - proposed_cost
        spent_this_pass = 0
        for sig in strat.find_buys(market_list, budget):
            if _has_open_position(conn, sig.item_id):
                continue
            m = markets.get(sig.item_id)
            if m is None or m.low is None or m.high is None:
                continue
            # don't act on stale or spiked prices — see _price_age_s / _is_spike
            age = _price_age_s(m, epoch_now)
            if max_age > 0 and age is not None and age > max_age:
                continue
            if _is_spike(m, spike_factor):
                continue
            if (m.high - ge_tax(m.high) - sig.price) < min_margin:
                continue
            # cumulative 4h GE buy limit: cap qty by what's left of the limit
            # after units already bought in the last 4h (across runs).
            qty = sig.qty
            if m.buy_limit and m.buy_limit > 0:
                remaining = m.buy_limit - _recent_bought_qty(conn, sig.item_id, now_dt)
                qty = min(qty, remaining)
                if qty <= 0:
                    continue
            cost = sig.price * qty
            if cost > budget - spent_this_pass:
                continue
            name = m.name if m else str(sig.item_id)
            pos_mod.create_proposed(
                conn, strategy=run["strategy"], item_id=sig.item_id,
                item_name=name, buy_price=sig.price, qty=qty,
                run_id=run["id"], params=params)
            spent_this_pass += cost

    # --- prune stale proposals ---
    for p in pos_mod.list_positions(conn, state="proposed"):
        m = markets.get(p["item_id"])
        if m is None:
            continue  # no fresh data — leave untouched
        sparams = json.loads(p["params_json"]) if p["params_json"] else {}
        strat = _make_strategy(p["strategy"], sparams, loader)
        if strat is None:
            continue
        signals = strat.find_buys([m], 10**15)
        still_wanted = any(s.item_id == p["item_id"] for s in signals)
        if not still_wanted:
            pos_mod.dismiss(conn, p["id"])

    # --- sell recommendations, per filled position (one signal per position) ---
    for p in pos_mod.list_positions(conn, state="filled"):
        m = markets.get(p["item_id"])
        if m is None:
            continue
        pos_mod.update_high_water(conn, p["id"], m.high)
        sparams = json.loads(p["params_json"]) if p["params_json"] else {}
        strat = _make_strategy(p["strategy"], sparams, loader)
        if strat is None:
            continue
        view = position_view(pos_mod.get(conn, p["id"]))
        decision = strat.should_sell(view, m)
        if not decision.sell:
            continue
        exists = conn.execute(
            "SELECT 1 FROM signals WHERE position_id=? AND type='sell' "
            "AND status='shown' LIMIT 1", (p["id"],)).fetchone()
        if exists:
            continue
        conn.execute(
            "INSERT INTO signals(item_id, position_id, strategy, type, price, "
            "reason, created_at, status) VALUES(?, ?, ?, 'sell', ?, ?, ?, 'shown')",
            (p["item_id"], p["id"], p["strategy"], m.high, decision.reason,
             _now_iso()))
        conn.commit()
