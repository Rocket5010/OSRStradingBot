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


def ensure_auto_run(conn, strategy, budget, params=None):
    """Ensure exactly one running auto-run exists with the given strategy, budget
    and (tuned) params. Creates it if absent, else updates in place when any of
    them changed (so open positions keep their own strategy/params for selling).
    Returns the run id."""
    params_json = json.dumps(params or {})
    row = conn.execute(
        "SELECT * FROM strategy_runs WHERE auto=1 AND state='running' LIMIT 1"
    ).fetchone()
    if row is None:
        cur = conn.execute(
            "INSERT INTO strategy_runs(strategy, params_json, budget_gp, spent_gp, "
            "state, started_at, auto) VALUES(?, ?, ?, 0, 'running', ?, 1)",
            (strategy, params_json, budget, _now()))
        conn.commit()
        return cur.lastrowid
    if (row["strategy"] != strategy or row["budget_gp"] != budget
            or (row["params_json"] or "{}") != params_json):
        conn.execute(
            "UPDATE strategy_runs SET strategy=?, budget_gp=?, params_json=? WHERE id=?",
            (strategy, budget, params_json, row["id"]))
        conn.commit()
    return row["id"]


def ensure_auto_runs(conn, specs):
    """Diversified auto-pilot: keep exactly one running auto-run per strategy in
    `specs` (a list of (strategy, budget, params)). Updates budget/params in
    place, creates missing ones, and stops auto-runs whose strategy dropped out
    of `specs`. Stopping a run does NOT touch its open positions — the engine's
    sell loop runs over filled positions regardless of run state, so a dropped
    strategy keeps selling what it bought. Returns {strategy: run_id}."""
    want = {strategy: (budget, params) for strategy, budget, params in specs}
    existing = conn.execute(
        "SELECT * FROM strategy_runs WHERE auto=1 AND state='running'").fetchall()
    result, seen = {}, set()
    for row in existing:
        strat = row["strategy"]
        if strat in want and strat not in seen:
            budget, params = want[strat]
            pj = json.dumps(params or {})
            if row["budget_gp"] != budget or (row["params_json"] or "{}") != pj:
                conn.execute(
                    "UPDATE strategy_runs SET budget_gp=?, params_json=? WHERE id=?",
                    (budget, pj, row["id"]))
            seen.add(strat)
            result[strat] = row["id"]
        else:
            # strategy no longer wanted (or a duplicate row) -> stop it
            conn.execute(
                "UPDATE strategy_runs SET state='stopped', stopped_at=? WHERE id=?",
                (_now(), row["id"]))
    for strat, (budget, params) in want.items():
        if strat not in seen:
            cur = conn.execute(
                "INSERT INTO strategy_runs(strategy, params_json, budget_gp, "
                "spent_gp, state, started_at, auto) "
                "VALUES(?, ?, ?, 0, 'running', ?, 1)",
                (strat, json.dumps(params or {}), budget, _now()))
            result[strat] = cur.lastrowid
    conn.commit()
    return result


def available(conn, run_id):
    r = get_run(conn, run_id)
    return r["budget_gp"] - r["spent_gp"] if r else 0
