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
    started_at TEXT, stopped_at TEXT
);
CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS price_cache (
    item_id INTEGER PRIMARY KEY,
    low INTEGER, high INTEGER, vol_1h INTEGER, ts TEXT
);
"""


def connect(path):
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db(conn):
    conn.executescript(SCHEMA)
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
