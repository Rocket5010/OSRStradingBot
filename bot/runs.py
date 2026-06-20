# bot/runs.py
"""Manage strategy_runs: manual start/stop with a per-run gp budget."""

import json
from datetime import datetime, timezone


def _now():
    return datetime.now(timezone.utc).isoformat()


def start_run(conn, strategy, budget_gp, params=None):
    cur = conn.execute(
        "INSERT INTO strategy_runs(strategy, params_json, budget_gp, spent_gp, "
        "state, started_at) VALUES(?, ?, ?, 0, 'running', ?)",
        (strategy, json.dumps(params or {}), budget_gp, _now()),
    )
    conn.commit()
    return cur.lastrowid


def stop_run(conn, run_id):
    conn.execute(
        "UPDATE strategy_runs SET state='stopped', stopped_at=? WHERE id=?",
        (_now(), run_id),
    )
    conn.commit()


def get_run(conn, run_id):
    return conn.execute(
        "SELECT * FROM strategy_runs WHERE id=?", (run_id,)
    ).fetchone()


def list_runs(conn, state=None):
    if state:
        return conn.execute(
            "SELECT * FROM strategy_runs WHERE state=? ORDER BY id", (state,)
        ).fetchall()
    return conn.execute("SELECT * FROM strategy_runs ORDER BY id").fetchall()


def add_spent(conn, run_id, delta):
    conn.execute(
        "UPDATE strategy_runs SET spent_gp = spent_gp + ? WHERE id=?",
        (delta, run_id),
    )
    conn.commit()


def ensure_auto_run(conn, strategy, budget):
    """Ensure exactly one running auto-run exists with the given strategy+budget.
    Creates it if absent, else updates strategy/budget in place (so open
    positions keep their own strategy for selling). Returns the run id."""
    row = conn.execute(
        "SELECT * FROM strategy_runs WHERE auto=1 AND state='running' LIMIT 1"
    ).fetchone()
    if row is None:
        cur = conn.execute(
            "INSERT INTO strategy_runs(strategy, params_json, budget_gp, spent_gp, "
            "state, started_at, auto) VALUES(?, '{}', ?, 0, 'running', ?, 1)",
            (strategy, budget, _now()))
        conn.commit()
        return cur.lastrowid
    if row["strategy"] != strategy or row["budget_gp"] != budget:
        conn.execute(
            "UPDATE strategy_runs SET strategy=?, budget_gp=? WHERE id=?",
            (strategy, budget, row["id"]))
        conn.commit()
    return row["id"]


def available(conn, run_id):
    r = get_run(conn, run_id)
    return r["budget_gp"] - r["spent_gp"] if r else 0
