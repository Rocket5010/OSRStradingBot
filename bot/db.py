"""SQLite schema and helpers. See the Data Model spec note."""

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    item_name TEXT NOT NULL,
    strategy TEXT NOT NULL,
    run_id INTEGER,
    state TEXT NOT NULL,
    buy_price INTEGER, qty INTEGER, buy_tax INTEGER,
    sell_target INTEGER, stop_loss INTEGER, max_hold_until TEXT,
    high_water INTEGER, ref_price INTEGER,
    params_json TEXT,
    sell_price INTEGER, realized_pl INTEGER,
    created_at TEXT, filled_at TEXT, closed_at TEXT
);
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    position_id INTEGER,
    strategy TEXT NOT NULL,
    type TEXT NOT NULL,
    price INTEGER, margin INTEGER, roi REAL,
    reason TEXT, created_at TEXT,
    status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS strategy_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy TEXT NOT NULL,
    params_json TEXT NOT NULL,
    budget_gp INTEGER NOT NULL,
    spent_gp INTEGER NOT NULL DEFAULT 0,
    state TEXT NOT NULL,
    auto INTEGER NOT NULL DEFAULT 0,
    started_at TEXT, stopped_at TEXT
);
CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS price_cache (
    item_id INTEGER PRIMARY KEY,
    low INTEGER, high INTEGER, vol_1h INTEGER, ts TEXT,
    high_time INTEGER, low_time INTEGER
);
CREATE TABLE IF NOT EXISTS item_meta (
    item_id INTEGER PRIMARY KEY,
    name TEXT
);
"""


def connect(path):
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


# Columns added after the initial release. For databases created before those
# columns existed, init_db adds them so `git pull` + restart upgrades in place
# without losing logged positions/config. (CREATE TABLE IF NOT EXISTS does not
# alter existing tables, so we migrate explicitly.)
_MIGRATIONS = {
    "positions": [("high_water", "INTEGER"), ("ref_price", "INTEGER"), ("params_json", "TEXT")],
    "signals": [("position_id", "INTEGER")],
    "strategy_runs": [("auto", "INTEGER NOT NULL DEFAULT 0")],
    "price_cache": [("high_time", "INTEGER"), ("low_time", "INTEGER")],
}


def _migrate(conn):
    for table, cols in _MIGRATIONS.items():
        existing = {r["name"]
                    for r in conn.execute(f"PRAGMA table_info({table})")}
        if not existing:
            continue  # table doesn't exist yet; SCHEMA already created it
        for name, decl in cols:
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


def init_db(conn):
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.commit()


def set_config(conn, key, value):
    conn.execute(
        "INSERT INTO config(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    conn.commit()


def get_config(conn, key, default=None):
    row = conn.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def save_item_names(conn, mapping):
    """Persist item_id -> name from a mapping dict {id: {"name": ...}}."""
    rows = []
    for key, meta in mapping.items():
        name = meta.get("name") if isinstance(meta, dict) else None
        rows.append((int(key), name))
    conn.executemany(
        "INSERT INTO item_meta(item_id, name) VALUES(?, ?) "
        "ON CONFLICT(item_id) DO UPDATE SET name=excluded.name", rows)
    conn.commit()


def get_item_names(conn):
    return {r["item_id"]: r["name"]
            for r in conn.execute("SELECT item_id, name FROM item_meta")}


def reset_state(conn):
    """Clear all trading state (positions, signals, strategy_runs, price_cache)
    and the curated watchlist. User settings (capital, bond_*, notify_webhook,
    curate_*) are preserved. For a full wipe, delete the database file instead."""
    for table in ("positions", "signals", "strategy_runs", "price_cache"):
        conn.execute(f"DELETE FROM {table}")
    conn.execute("DELETE FROM config WHERE key='watchlist'")
    conn.commit()
