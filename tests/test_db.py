from bot import db


def test_init_creates_all_tables():
    conn = db.connect(":memory:")
    db.init_db(conn)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    names = {r["name"] for r in rows}
    assert names == {"positions", "signals", "strategy_runs", "config", "price_cache"}


def test_init_is_idempotent():
    conn = db.connect(":memory:")
    db.init_db(conn)
    db.init_db(conn)  # must not raise
    assert conn.execute("SELECT COUNT(*) c FROM positions").fetchone()["c"] == 0


def test_config_set_and_get():
    conn = db.connect(":memory:")
    db.init_db(conn)
    db.set_config(conn, "capital", "42000000")
    assert db.get_config(conn, "capital") == "42000000"
    assert db.get_config(conn, "missing", default="x") == "x"
