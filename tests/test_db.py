from bot import db


def test_init_creates_all_tables():
    conn = db.connect(":memory:")
    db.init_db(conn)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    names = {r["name"] for r in rows}
    assert names == {"positions", "signals", "strategy_runs", "config", "price_cache", "item_meta"}


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


def test_connect_sets_busy_timeout():
    conn = db.connect(":memory:")
    assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000


def test_init_db_migrates_missing_columns():
    # simulate an OLD database created before high_water/ref_price/position_id
    conn = db.connect(":memory:")
    conn.execute("CREATE TABLE positions (id INTEGER PRIMARY KEY, item_id INTEGER, "
                 "item_name TEXT, strategy TEXT, state TEXT, buy_price INTEGER, qty INTEGER)")
    conn.execute("CREATE TABLE signals (id INTEGER PRIMARY KEY, item_id INTEGER, strategy TEXT)")
    conn.commit()
    db.init_db(conn)   # should add the new columns, not crash
    pcols = {r["name"] for r in conn.execute("PRAGMA table_info(positions)")}
    scols = {r["name"] for r in conn.execute("PRAGMA table_info(signals)")}
    assert {"high_water", "ref_price"} <= pcols
    assert "position_id" in scols


def test_init_db_migration_is_idempotent():
    conn = db.connect(":memory:")
    db.init_db(conn)
    db.init_db(conn)   # running twice must not error (columns already present)
    pcols = {r["name"] for r in conn.execute("PRAGMA table_info(positions)")}
    assert "high_water" in pcols


def test_save_and_get_item_names():
    conn = db.connect(":memory:")
    db.init_db(conn)
    db.save_item_names(conn, {"4151": {"name": "Abyssal whip"},
                              "1515": {"name": "Yew logs"}})
    names = db.get_item_names(conn)
    assert names[4151] == "Abyssal whip" and names[1515] == "Yew logs"
    db.save_item_names(conn, {"4151": {"name": "Whip"}})
    assert db.get_item_names(conn)[4151] == "Whip"


def test_reset_state_clears_trading_keeps_settings():
    conn = db.connect(":memory:")
    db.init_db(conn)
    db.set_config(conn, "capital", "100")
    db.set_config(conn, "watchlist", "1,2,3")
    conn.execute("INSERT INTO positions(item_id,item_name,strategy,state,buy_price,qty) "
                 "VALUES(1,'x','rsi','proposed',10,1)")
    conn.execute("INSERT INTO strategy_runs(strategy,params_json,budget_gp,spent_gp,state) "
                 "VALUES('rsi','{}',100,0,'running')")
    conn.execute("INSERT INTO price_cache(item_id,low,high,vol_1h,ts) VALUES(1,1,2,3,'t')")
    conn.commit()
    db.reset_state(conn)
    assert conn.execute("SELECT COUNT(*) c FROM positions").fetchone()["c"] == 0
    assert conn.execute("SELECT COUNT(*) c FROM strategy_runs").fetchone()["c"] == 0
    assert conn.execute("SELECT COUNT(*) c FROM price_cache").fetchone()["c"] == 0
    assert db.get_config(conn, "watchlist") is None       # watchlist cleared
    assert db.get_config(conn, "capital") == "100"        # setting kept
