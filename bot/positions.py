# bot/positions.py
"""Position lifecycle: proposed -> accepted -> filled -> selling -> sold,
with dismiss/cancel branches. Commits/releases run capital and computes P/L."""

from datetime import datetime, timezone

from bot.tax import ge_tax
from bot import runs as runs_mod


def _now():
    return datetime.now(timezone.utc).isoformat()


def create_proposed(conn, strategy, item_id, item_name, buy_price, qty,
                    run_id=None, sell_target=None, stop_loss=None, ref_price=None):
    cur = conn.execute(
        "INSERT INTO positions(item_id, item_name, strategy, run_id, state, "
        "buy_price, qty, sell_target, stop_loss, high_water, ref_price, created_at) "
        "VALUES(?, ?, ?, ?, 'proposed', ?, ?, ?, ?, ?, ?, ?)",
        (item_id, item_name, strategy, run_id, buy_price, qty,
         sell_target, stop_loss, buy_price, ref_price, _now()),
    )
    conn.commit()
    return cur.lastrowid


def update_high_water(conn, pid, price):
    """Raise the position's high-water mark if price exceeds it."""
    conn.execute(
        "UPDATE positions SET high_water = MAX(high_water, ?) WHERE id=?",
        (price, pid))
    conn.commit()


def get(conn, pid):
    return conn.execute("SELECT * FROM positions WHERE id=?", (pid,)).fetchone()


def list_positions(conn, state=None):
    if state:
        return conn.execute(
            "SELECT * FROM positions WHERE state=? ORDER BY id", (state,)
        ).fetchall()
    return conn.execute("SELECT * FROM positions ORDER BY id").fetchall()


def _require(pos, *allowed):
    if pos["state"] not in allowed:
        raise ValueError(
            f"position {pos['id']} is '{pos['state']}', expected one of {allowed}")


def _committed(pos):
    return pos["buy_price"] * pos["qty"]


def accept(conn, pid):
    p = get(conn, pid)
    _require(p, "proposed")
    conn.execute("UPDATE positions SET state='accepted' WHERE id=?", (pid,))
    if p["run_id"]:
        runs_mod.add_spent(conn, p["run_id"], _committed(p))
    conn.commit()


def mark_filled(conn, pid):
    p = get(conn, pid)
    _require(p, "accepted")
    conn.execute("UPDATE positions SET state='filled', filled_at=? WHERE id=?",
                 (_now(), pid))
    conn.commit()


def start_selling(conn, pid):
    p = get(conn, pid)
    _require(p, "filled")
    conn.execute("UPDATE positions SET state='selling' WHERE id=?", (pid,))
    conn.commit()


def mark_sold(conn, pid, sell_price):
    p = get(conn, pid)
    _require(p, "selling")
    qty = p["qty"]
    pl = (sell_price - ge_tax(sell_price)) * qty - p["buy_price"] * qty
    conn.execute(
        "UPDATE positions SET state='sold', sell_price=?, realized_pl=?, "
        "closed_at=? WHERE id=?", (sell_price, pl, _now(), pid))
    if p["run_id"]:
        runs_mod.add_spent(conn, p["run_id"], -_committed(p))
    conn.commit()
    return pl


def cancel(conn, pid):
    p = get(conn, pid)
    _require(p, "accepted", "filled", "selling")
    conn.execute("UPDATE positions SET state='cancelled', closed_at=? WHERE id=?",
                 (_now(), pid))
    if p["run_id"]:
        runs_mod.add_spent(conn, p["run_id"], -_committed(p))
    conn.commit()


def dismiss(conn, pid):
    p = get(conn, pid)
    _require(p, "proposed")
    conn.execute("UPDATE positions SET state='dismissed', closed_at=? WHERE id=?",
                 (_now(), pid))
    conn.commit()
