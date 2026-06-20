from bot import db, runs


def fresh():
    conn = db.connect(":memory:")
    db.init_db(conn)
    return conn


def test_start_run_creates_running():
    conn = fresh()
    rid = runs.start_run(conn, "mean_reversion", budget_gp=10_000_000, params={"k": 2})
    r = runs.get_run(conn, rid)
    assert r["strategy"] == "mean_reversion"
    assert r["budget_gp"] == 10_000_000
    assert r["spent_gp"] == 0
    assert r["state"] == "running"


def test_stop_run():
    conn = fresh()
    rid = runs.start_run(conn, "rsi", budget_gp=5_000_000)
    runs.stop_run(conn, rid)
    assert runs.get_run(conn, rid)["state"] == "stopped"


def test_list_runs_filters_state():
    conn = fresh()
    a = runs.start_run(conn, "rsi", 1)
    b = runs.start_run(conn, "bollinger", 1)
    runs.stop_run(conn, b)
    running = runs.list_runs(conn, state="running")
    assert {r["id"] for r in running} == {a}


def test_ensure_auto_run_creates_one():
    conn = fresh()
    rid = runs.ensure_auto_run(conn, "breakout", 500_000_000)
    row = runs.get_run(conn, rid)
    assert row["auto"] == 1 and row["strategy"] == "breakout"
    assert row["budget_gp"] == 500_000_000 and row["state"] == "running"


def test_ensure_auto_run_updates_in_place():
    conn = fresh()
    rid1 = runs.ensure_auto_run(conn, "breakout", 500_000_000)
    rid2 = runs.ensure_auto_run(conn, "momentum", 400_000_000)
    assert rid1 == rid2                       # same run, not a new one
    row = runs.get_run(conn, rid2)
    assert row["strategy"] == "momentum" and row["budget_gp"] == 400_000_000
    n = conn.execute("SELECT COUNT(*) c FROM strategy_runs WHERE auto=1").fetchone()["c"]
    assert n == 1


def test_spent_and_available():
    conn = fresh()
    rid = runs.start_run(conn, "rsi", budget_gp=1000)
    runs.add_spent(conn, rid, 300)
    assert runs.available(conn, rid) == 700
    runs.add_spent(conn, rid, -100)
    assert runs.available(conn, rid) == 800
