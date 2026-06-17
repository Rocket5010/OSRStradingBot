# bot/engine_live.py
"""Live decision pass: turn running strategies + market data into proposed
positions and sell recommendations."""

import json
import os
from datetime import datetime, timezone

from bot import runs as runs_mod
from bot import positions as pos_mod
from bot.market import position_view
from bot.strategies.loader import load_strategies

_OPEN_STATES = ("proposed", "accepted", "filled", "selling")
_STRATEGIES_DIR = os.path.join(os.path.dirname(__file__), "strategies")


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _make_strategy(name, params, loader):
    found = loader(_STRATEGIES_DIR)
    proto = found.get(name)
    if proto is None:
        return None
    # rebuild with the run's params if the class supports it
    try:
        return type(proto)(**params)
    except TypeError:
        return proto


def _has_open_position(conn, run_id, item_id):
    row = conn.execute(
        "SELECT 1 FROM positions WHERE run_id=? AND item_id=? "
        f"AND state IN ({','.join('?' * len(_OPEN_STATES))}) LIMIT 1",
        (run_id, item_id, *_OPEN_STATES)).fetchone()
    return row is not None


def evaluate(conn, markets, now, loader=load_strategies):
    """markets: {item_id: MarketData}. Creates buy proposals for running runs
    and sell-recommendation signals for filled positions."""
    market_list = list(markets.values())

    # --- buys, per running run ---
    for run in runs_mod.list_runs(conn, state="running"):
        params = json.loads(run["params_json"] or "{}")
        strat = _make_strategy(run["strategy"], params, loader)
        if strat is None:
            continue
        budget = runs_mod.available(conn, run["id"])
        for sig in strat.find_buys(market_list, budget):
            if _has_open_position(conn, run["id"], sig.item_id):
                continue
            m = markets.get(sig.item_id)
            name = m.name if m else str(sig.item_id)
            pos_mod.create_proposed(
                conn, strategy=run["strategy"], item_id=sig.item_id,
                item_name=name, buy_price=sig.price, qty=sig.qty,
                run_id=run["id"])

    # --- sell recommendations, per filled position ---
    for p in pos_mod.list_positions(conn, state="filled"):
        m = markets.get(p["item_id"])
        if m is None:
            continue
        pos_mod.update_high_water(conn, p["id"], m.high)
        strat = _make_strategy(p["strategy"], {}, loader)
        if strat is None:
            continue
        view = position_view(pos_mod.get(conn, p["id"]))
        decision = strat.should_sell(view, m)
        if not decision.sell:
            continue
        exists = conn.execute(
            "SELECT 1 FROM signals WHERE item_id=? AND strategy=? AND type='sell' "
            "AND status='shown' LIMIT 1", (p["item_id"], p["strategy"])).fetchone()
        if exists:
            continue
        conn.execute(
            "INSERT INTO signals(item_id, strategy, type, price, reason, "
            "created_at, status) VALUES(?, ?, 'sell', ?, ?, ?, 'shown')",
            (p["item_id"], p["strategy"], m.high, decision.reason, _now_iso()))
        conn.commit()
