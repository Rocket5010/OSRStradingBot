# Phase 1 — Core Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> Index: [[Home]] · Spec: [[OSRS Flip Bot Design Spec]] · Phases: [[Build Phases]]

**Goal:** Build the foundation of the OSRS Flip Bot — fetch market data from the OSRS Wiki API, persist state in SQLite, define the pluggable strategy contract with auto-discovery, and orchestrate a single poll cycle.

**Architecture:** A single Python package (`bot/`). `api_client` wraps the [[OSRS Wiki API]] with rate-limiting. `db` owns the SQLite [[Data Model|schema]]. `strategies/base` defines the [[Strategy System|Strategy contract]] and signal dataclasses. `strategy_loader` auto-discovers strategy files. `poller` runs one fetch→snapshot→cache cycle. No web, no strategies yet (those are later phases).

**Tech Stack:** Python 3.13, stdlib `urllib` + `sqlite3` (no runtime deps), `pytest` for tests.

---

## File Structure

```
OSRS invester/
├── bot/
│   ├── __init__.py
│   ├── api_client.py        # WikiClient: fetch + rate-limit + parse
│   ├── db.py                # SQLite schema + connection
│   ├── poller.py            # one poll cycle: fetch → cache
│   └── strategies/
│       ├── __init__.py
│       ├── base.py          # Strategy ABC + MarketData/BuySignal/SellDecision
│       └── loader.py        # auto-discover Strategy subclasses
├── tests/
│   ├── __init__.py
│   ├── test_api_client.py
│   ├── test_db.py
│   ├── test_base.py
│   ├── test_loader.py
│   └── test_poller.py
├── pyproject.toml
└── flip_finder.py           # existing MVP, untouched
```

---

### Task 0: Project setup

**Files:**
- Create: `pyproject.toml`
- Create: `bot/__init__.py`, `bot/strategies/__init__.py`, `tests/__init__.py`

- [ ] **Step 1: Install pytest**

Run: `python -m pip install pytest`
Expected: installs pytest successfully.

- [ ] **Step 2: Create `pyproject.toml`**

```toml
[project]
name = "osrs-flip-bot"
version = "0.1.0"
requires-python = ">=3.13"

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v"
```

- [ ] **Step 3: Create empty package files**

Create `bot/__init__.py` (empty), `bot/strategies/__init__.py` (empty), `tests/__init__.py` (empty).

- [ ] **Step 4: Verify pytest runs**

Run: `python -m pytest`
Expected: "no tests ran" (exit 5) — confirms pytest is wired.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml bot/ tests/
git commit -m "chore: scaffold bot package and pytest"
```

---

### Task 1: API client — rate-limited fetch

**Files:**
- Create: `bot/api_client.py`
- Test: `tests/test_api_client.py`

The client exposes `latest`, `five_min`, `one_hour`, `mapping`, `timeseries`. All HTTP goes through one overridable method `_get(path)` so tests inject fake responses without network.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_client.py
from bot.api_client import WikiClient


class FakeClient(WikiClient):
    def __init__(self, payloads):
        super().__init__(user_agent="test")
        self.payloads = payloads
        self.calls = []

    def _get(self, path):
        self.calls.append(path)
        return self.payloads[path]


def test_latest_returns_data_dict():
    c = FakeClient({"/latest": {"data": {"2": {"high": 200, "low": 150}}}})
    assert c.latest() == {"2": {"high": 200, "low": 150}}


def test_mapping_returns_list():
    c = FakeClient({"/mapping": [{"id": 2, "name": "Cannonball", "limit": 11000}]})
    assert c.mapping()[0]["name"] == "Cannonball"


def test_timeseries_builds_path_with_params():
    c = FakeClient({"/timeseries?timestep=24h&id=2": {"data": [{"avgHighPrice": 100}]}})
    out = c.timeseries(2, "24h")
    assert out == [{"avgHighPrice": 100}]
    assert c.calls == ["/timeseries?timestep=24h&id=2"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_api_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.api_client'`.

- [ ] **Step 3: Write minimal implementation**

```python
# bot/api_client.py
"""Client for the OSRS Wiki Real-time Prices API. Stdlib only."""

import json
import time
import urllib.request
import urllib.error

BASE_URL = "https://prices.runescape.wiki/api/v1/osrs"


class WikiClient:
    def __init__(self, user_agent, base_url=BASE_URL, min_interval=1.0):
        self.user_agent = user_agent
        self.base_url = base_url
        self.min_interval = min_interval
        self._last_call = 0.0

    def _get(self, path):
        """Rate-limited HTTP GET. Returns parsed JSON. Override in tests."""
        wait = self.min_interval - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise ApiError(f"request failed for {url}: {e}") from e
        finally:
            self._last_call = time.monotonic()
        return data

    def latest(self):
        return self._get("/latest")["data"]

    def five_min(self):
        return self._get("/5m")["data"]

    def one_hour(self):
        return self._get("/1h")["data"]

    def mapping(self):
        return self._get("/mapping")

    def timeseries(self, item_id, timestep):
        return self._get(f"/timeseries?timestep={timestep}&id={item_id}")["data"]


class ApiError(Exception):
    pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_api_client.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add bot/api_client.py tests/test_api_client.py
git commit -m "feat: add WikiClient with rate-limited fetch"
```

---

### Task 2: Database — schema + connection

**Files:**
- Create: `bot/db.py`
- Test: `tests/test_db.py`

Implements the full [[Data Model]] schema. `connect(path)` returns a sqlite3 connection with row factory; `init_db(conn)` creates all tables idempotently.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_db.py
from bot import db


def test_init_creates_all_tables():
    conn = db.connect(":memory:")
    db.init_db(conn)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_db.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.db'`.

- [ ] **Step 3: Write minimal implementation**

```python
# bot/db.py
"""SQLite schema and helpers. See the Data Model spec note."""

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    item_name TEXT NOT NULL,
    strategy TEXT NOT NULL,
    run_id INTEGER,
    state TEXT NOT NULL,           -- proposed|accepted|filled|selling|sold|cancelled|dismissed
    buy_price INTEGER, qty INTEGER, buy_tax INTEGER,
    sell_target INTEGER, stop_loss INTEGER, max_hold_until TEXT,
    sell_price INTEGER, realized_pl INTEGER,
    created_at TEXT, filled_at TEXT, closed_at TEXT
);
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    strategy TEXT NOT NULL,
    type TEXT NOT NULL,            -- buy|sell
    price INTEGER, margin INTEGER, roi REAL,
    reason TEXT, created_at TEXT,
    status TEXT NOT NULL           -- shown|accepted|dismissed
);
CREATE TABLE IF NOT EXISTS strategy_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy TEXT NOT NULL,
    params_json TEXT NOT NULL,
    budget_gp INTEGER NOT NULL,
    spent_gp INTEGER NOT NULL DEFAULT 0,
    state TEXT NOT NULL,           -- running|stopped
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
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_db.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add bot/db.py tests/test_db.py
git commit -m "feat: add SQLite schema and config helpers"
```

---

### Task 3: Strategy contract — base types

**Files:**
- Create: `bot/strategies/base.py`
- Test: `tests/test_base.py`

Defines the dataclasses passed to/from strategies and the abstract `Strategy`. See [[Strategy System]]. `MarketData` is the per-item snapshot a strategy reads; `BuySignal`/`SellDecision` are its outputs.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_base.py
import pytest
from bot.strategies.base import Strategy, MarketData, BuySignal, SellDecision


def test_marketdata_holds_fields():
    md = MarketData(item_id=2, name="Cannonball", low=150, high=200, vol_1h=5000, history=[])
    assert md.item_id == 2 and md.high == 200


def test_buysignal_defaults():
    sig = BuySignal(item_id=2, price=150, qty=10, reason="cheap")
    assert sig.qty == 10 and sig.reason == "cheap"


def test_selldecision_sell_flag():
    d = SellDecision(sell=True, reason="target hit")
    assert d.sell is True


def test_strategy_is_abstract():
    with pytest.raises(TypeError):
        Strategy()  # cannot instantiate abstract base


def test_concrete_strategy_works():
    class Dummy(Strategy):
        name = "dummy"
        description = "test"
        def find_buys(self, market, budget):
            return [BuySignal(item_id=2, price=10, qty=1, reason="x")]
        def should_sell(self, position, market):
            return SellDecision(sell=False, reason="hold")
        def default_params(self):
            return {"min_margin": 50}

    d = Dummy()
    assert d.find_buys([], 1000)[0].item_id == 2
    assert d.should_sell(None, None).sell is False
    assert d.default_params()["min_margin"] == 50
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_base.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.strategies.base'`.

- [ ] **Step 3: Write minimal implementation**

```python
# bot/strategies/base.py
"""Strategy contract and signal datatypes. See the Strategy System spec note."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class MarketData:
    item_id: int
    name: str
    low: int            # instant-buy price
    high: int           # instant-sell price
    vol_1h: int
    history: list = field(default_factory=list)   # timeseries candles, if loaded


@dataclass
class BuySignal:
    item_id: int
    price: int
    qty: int
    reason: str


@dataclass
class SellDecision:
    sell: bool
    reason: str


class Strategy(ABC):
    name: str
    description: str

    @abstractmethod
    def find_buys(self, market, budget):
        """Return list[BuySignal] within the given gp budget."""

    @abstractmethod
    def should_sell(self, position, market):
        """Return a SellDecision for a held position."""

    @abstractmethod
    def default_params(self):
        """Return a dict of tunable params with default values."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_base.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add bot/strategies/base.py tests/test_base.py
git commit -m "feat: add Strategy contract and signal dataclasses"
```

---

### Task 4: Strategy loader — auto-discovery

**Files:**
- Create: `bot/strategies/loader.py`
- Test: `tests/test_loader.py`

`load_strategies(dir)` imports every `.py` file in a directory (except `base.py`, `loader.py`, `__init__.py`), finds concrete `Strategy` subclasses, and returns `{name: instance}`. See [[Strategy System]].

- [ ] **Step 1: Write the failing test**

```python
# tests/test_loader.py
from bot.strategies.loader import load_strategies

STRAT_SRC = '''
from bot.strategies.base import Strategy, SellDecision

class MyStrat(Strategy):
    name = "mystrat"
    description = "demo"
    def find_buys(self, market, budget): return []
    def should_sell(self, position, market): return SellDecision(sell=False, reason="")
    def default_params(self): return {}
'''


def test_loads_strategy_from_dir(tmp_path):
    (tmp_path / "mystrat.py").write_text(STRAT_SRC)
    found = load_strategies(str(tmp_path))
    assert "mystrat" in found
    assert found["mystrat"].description == "demo"


def test_ignores_non_strategy_files(tmp_path):
    (tmp_path / "notes.py").write_text("x = 1\n")
    found = load_strategies(str(tmp_path))
    assert found == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_loader.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.strategies.loader'`.

- [ ] **Step 3: Write minimal implementation**

```python
# bot/strategies/loader.py
"""Auto-discover Strategy subclasses from a directory."""

import importlib.util
import inspect
import os

from bot.strategies.base import Strategy

_SKIP = {"base.py", "loader.py", "__init__.py"}


def load_strategies(directory):
    found = {}
    for fname in sorted(os.listdir(directory)):
        if not fname.endswith(".py") or fname in _SKIP:
            continue
        path = os.path.join(directory, fname)
        mod_name = f"_strategy_{fname[:-3]}"
        spec = importlib.util.spec_from_file_location(mod_name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, Strategy) and obj is not Strategy:
                instance = obj()
                found[instance.name] = instance
    return found
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_loader.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add bot/strategies/loader.py tests/test_loader.py
git commit -m "feat: add strategy auto-discovery loader"
```

---

### Task 5: Poller — one cycle: fetch → cache

**Files:**
- Create: `bot/poller.py`
- Test: `tests/test_poller.py`

`poll_once(client, conn)` fetches `latest` + `one_hour`, merges them, writes a row per item to `price_cache`, and returns the count written. This is the unit a scheduler will call every 5 min (scheduling itself is a later phase). See [[Position Lifecycle]] / [[OSRS Wiki API]].

- [ ] **Step 1: Write the failing test**

```python
# tests/test_poller.py
from bot import db
from bot.poller import poll_once


class StubClient:
    def latest(self):
        return {"2": {"high": 200, "low": 150}, "4": {"high": 0, "low": 0}}
    def one_hour(self):
        return {"2": {"highPriceVolume": 300, "lowPriceVolume": 200}}


def test_poll_writes_price_cache():
    conn = db.connect(":memory:")
    db.init_db(conn)
    n = poll_once(StubClient(), conn)
    assert n == 2
    row = conn.execute("SELECT * FROM price_cache WHERE item_id=2").fetchone()
    assert row["low"] == 150 and row["high"] == 200 and row["vol_1h"] == 500


def test_poll_zero_volume_when_missing_in_1h():
    conn = db.connect(":memory:")
    db.init_db(conn)
    poll_once(StubClient(), conn)
    row = conn.execute("SELECT * FROM price_cache WHERE item_id=4").fetchone()
    assert row["vol_1h"] == 0


def test_poll_is_upsert():
    conn = db.connect(":memory:")
    db.init_db(conn)
    poll_once(StubClient(), conn)
    poll_once(StubClient(), conn)
    count = conn.execute("SELECT COUNT(*) c FROM price_cache").fetchone()["c"]
    assert count == 2  # not duplicated
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_poller.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.poller'`.

- [ ] **Step 3: Write minimal implementation**

```python
# bot/poller.py
"""One poll cycle: fetch latest + 1h volume, write to price_cache."""

from datetime import datetime, timezone


def poll_once(client, conn):
    latest = client.latest()
    one_hour = client.one_hour()
    ts = datetime.now(timezone.utc).isoformat()
    written = 0
    for item_id, lt in latest.items():
        vol = one_hour.get(item_id, {})
        vol_1h = (vol.get("highPriceVolume") or 0) + (vol.get("lowPriceVolume") or 0)
        conn.execute(
            "INSERT INTO price_cache(item_id, low, high, vol_1h, ts) "
            "VALUES(?, ?, ?, ?, ?) "
            "ON CONFLICT(item_id) DO UPDATE SET "
            "low=excluded.low, high=excluded.high, vol_1h=excluded.vol_1h, ts=excluded.ts",
            (int(item_id), lt.get("low"), lt.get("high"), vol_1h, ts),
        )
        written += 1
    conn.commit()
    return written
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_poller.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest`
Expected: PASS — all tests across all files green (15 passed).

- [ ] **Step 6: Commit**

```bash
git add bot/poller.py tests/test_poller.py
git commit -m "feat: add poll cycle writing price_cache"
```

---

## Self-Review Notes

- **Spec coverage (Phase 1 scope):** api_client incl. `/timeseries` ✓ (Task 1), full db schema incl. `strategy_runs` ✓ (Task 2), Strategy contract ✓ (Task 3), auto-discovery ✓ (Task 4), poll cycle ✓ (Task 5). Strategies themselves, backtest, web, dashboard, polish = later phases (out of scope here, by design).
- **Type consistency:** `find_buys(self, market, budget)` and `should_sell(self, position, market)` signatures match between `base.py` (Task 3), the loader test stub (Task 4), and future strategy files. `price_cache` columns (`item_id, low, high, vol_1h, ts`) match between `db.py` (Task 2) and `poller.py` (Task 5).
- **No placeholders:** every code step has complete code; every run step has expected output.

## Next Phase
After Phase 1 is green, write the Phase 2 plan ([[Build Phases|Strategies]]) — implements `margin_flip` + the investing strategies against this contract.
