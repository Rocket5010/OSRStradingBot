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


def test_spent_and_available():
    conn = fresh()
    rid = runs.start_run(conn, "rsi", budget_gp=1000)
    runs.add_spent(conn, rid, 300)
    assert runs.available(conn, rid) == 700
    runs.add_spent(conn, rid, -100)
    assert runs.available(conn, rid) == 800
