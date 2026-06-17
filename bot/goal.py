# bot/goal.py
"""Keep the bond-price goal config fresh. Bond is item 13190."""

from datetime import datetime, timezone

from bot import db

BOND_ID = 13190


def refresh_bond_goal(conn, client, now_iso=None):
    now_iso = now_iso or datetime.now(timezone.utc).isoformat()
    bond = client.latest_item(BOND_ID)
    db.set_config(conn, "bond_price", str(bond["high"]))
    if db.get_config(conn, "bond_days") is None:
        db.set_config(conn, "bond_days", "14")
    if db.get_config(conn, "goal_period_start") is None:
        db.set_config(conn, "goal_period_start", now_iso)
