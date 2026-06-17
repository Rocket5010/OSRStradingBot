# Phase 4b — Live Decision Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

> Index: [[Home]] · Spec: [[OSRS Flip Bot Design Spec]] · Phases: [[Build Phases]] · Prev: [[2026-06-16-phase-4a-api-state]]

**Goal:** Wire the "brain" — on each poll cycle, assemble market data (price_cache + cached `/timeseries`), run every RUNNING strategy's `find_buys` within its budget to create proposed positions, and recommend sells on filled positions whose strategy says exit. Run it on a background scheduler, served alongside the API.

**Architecture:** `bot/market.py` assembles `MarketData` per watchlist item and adapts a position Row into an attribute object (`PositionView`) for strategies. `bot/engine_live.py` holds `evaluate()` — the pure-ish decision pass (buys + sell recommendations, de-duplicated). `bot/scheduler.py` runs poll+evaluate every N seconds on a daemon thread with its OWN db connection. `bot/main.py` wires db + scheduler + uvicorn. Strategies access `position.buy_price`/`.high_water`/`.ref_price` as attributes, but DB rows are dict-like — `PositionView` bridges that gap.

**Tech Stack:** Python 3.13, stdlib `threading`, `fastapi`/`uvicorn`, `pytest`.

---

## File Structure

```
bot/
├── market.py          # HistoryCache, build_market_data, position_view
├── engine_live.py     # evaluate(conn, strategies_dir, markets, now)
├── scheduler.py       # PollScheduler (daemon thread, own connection)
└── main.py            # entry point: db + scheduler + uvicorn
tests/
├── test_market.py
├── test_engine_live.py
└── test_scheduler.py
```

---

### Task 1: Schema — high_water + ref_price on positions

**Files:**
- Modify: `bot/db.py`
- Modify: `bot/positions.py`
- Test: `tests/test_positions.py`

Strategies `breakout`/`crash_recovery` read `position.high_water`/`position.ref_price`. Store them on the row; the engine maintains `high_water`.

- [ ] **Step 1: Add a failing test**

Append to `tests/test_positions.py`:

```python
def test_high_water_and_ref_price_default_and_update():
    conn = fresh()
    pid = pos.create_proposed(conn, strategy="breakout", item_id=2, item_name="Cb",
                              buy_price=100, qty=10, ref_price=130)
    row = pos.get(conn, pid)
    assert row["ref_price"] == 130
    assert row["high_water"] == 100   # defaults to buy_price
    pos.update_high_water(conn, pid, 150)
    assert pos.get(conn, pid)["high_water"] == 150
    pos.update_high_water(conn, pid, 120)   # never decreases
    assert pos.get(conn, pid)["high_water"] == 150
```

- [ ] **Step 2: Run, verify failure**

Run: `python -m pytest tests/test_positions.py::test_high_water_and_ref_price_default_and_update -v`
Expected: FAIL — `sqlite3.OperationalError: no such column: ref_price` (or AttributeError on update_high_water).

- [ ] **Step 3: Add columns to the schema**

In `bot/db.py`, in the `positions` table DDL, add two columns after `stop_loss INTEGER`:

```python
    sell_target INTEGER, stop_loss INTEGER, max_hold_until TEXT,
    high_water INTEGER, ref_price INTEGER,
    sell_price INTEGER, realized_pl INTEGER,
```

- [ ] **Step 4: Set high_water/ref_price in create_proposed + add update_high_water**

In `bot/positions.py`, change `create_proposed` to accept `ref_price=None` and initialize `high_water` to `buy_price`:

```python
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
```

Add this function to `bot/positions.py`:

```python
def update_high_water(conn, pid, price):
    """Raise the position's high-water mark if price exceeds it."""
    conn.execute(
        "UPDATE positions SET high_water = MAX(high_water, ?) WHERE id=?",
        (price, pid))
    conn.commit()
```

- [ ] **Step 5: Run positions tests**

Run: `python -m pytest tests/test_positions.py -v`
Expected: PASS (all prior + the new test).

- [ ] **Step 6: Commit**

```bash
git add bot/db.py bot/positions.py tests/test_positions.py
git commit -m "feat: add high_water/ref_price to positions"
```

---

### Task 2: Market assembly + position adapter

**Files:**
- Create: `bot/market.py`
- Test: `tests/test_market.py`

`position_view` wraps a dict-like row in an attribute object for strategies. `HistoryCache` caches `/timeseries` per item, refetching only when stale (uses an injected `now` for testability). `build_market_data` joins price_cache + mapping + history into `MarketData`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_market.py
from bot import db
from bot.market import position_view, HistoryCache, build_market_data


def test_position_view_exposes_attributes():
    conn = db.connect(":memory:")
    db.init_db(conn)
    conn.execute("INSERT INTO positions(item_id,item_name,strategy,state,buy_price,"
                 "qty,high_water,ref_price) VALUES(2,'Cb','rsi','filled',100,10,150,130)")
    conn.commit()
    row = conn.execute("SELECT * FROM positions WHERE id=1").fetchone()
    v = position_view(row)
    assert v.buy_price == 100 and v.high_water == 150 and v.ref_price == 130


class StubClient:
    def __init__(self): self.calls = 0
    def timeseries(self, item_id, timestep):
        self.calls += 1
        return [{"avgHighPrice": 100, "avgLowPrice": 90}]


def test_history_cache_refetches_only_when_stale():
    client = StubClient()
    cache = HistoryCache(client, timestep="24h", max_age_s=300)
    t = [1000.0]
    cache.get(2, now=t[0])
    cache.get(2, now=t[0] + 100)   # within max_age -> cached
    assert client.calls == 1
    cache.get(2, now=t[0] + 400)   # stale -> refetch
    assert client.calls == 2


def test_build_market_data_joins_sources():
    conn = db.connect(":memory:")
    db.init_db(conn)
    conn.execute("INSERT INTO price_cache(item_id,low,high,vol_1h,ts) "
                 "VALUES(2,150,200,5000,'t')")
    conn.commit()
    mapping = {"2": {"name": "Cannonball", "limit": 11000, "members": False}}
    cache = HistoryCache(StubClient(), timestep="24h", max_age_s=300)
    markets = build_market_data(conn, mapping, cache, [2], now=0.0)
    assert len(markets) == 1
    m = markets[0]
    assert m.item_id == 2 and m.name == "Cannonball"
    assert m.low == 150 and m.high == 200 and m.vol_1h == 5000
    assert m.buy_limit == 11000 and m.members is False
    assert m.history == [{"avgHighPrice": 100, "avgLowPrice": 90}]


def test_build_skips_items_without_price_cache():
    conn = db.connect(":memory:")
    db.init_db(conn)
    mapping = {"2": {"name": "X", "limit": 0, "members": False}}
    cache = HistoryCache(StubClient(), timestep="24h", max_age_s=300)
    assert build_market_data(conn, mapping, cache, [2], now=0.0) == []
```

- [ ] **Step 2: Run, verify failure**

Run: `python -m pytest tests/test_market.py -v`
Expected: FAIL — no module `bot.market`.

- [ ] **Step 3: Implement market.py**

```python
# bot/market.py
"""Assemble MarketData from price_cache + mapping + cached timeseries, and
adapt position rows into attribute objects for strategies."""

from types import SimpleNamespace

from bot.strategies.base import MarketData


def position_view(row):
    """Wrap a dict-like position row so strategies can use attribute access."""
    return SimpleNamespace(**{k: row[k] for k in row.keys()})


class HistoryCache:
    """Caches /timeseries per item; refetches only when older than max_age_s."""

    def __init__(self, client, timestep="24h", max_age_s=21600):
        self.client = client
        self.timestep = timestep
        self.max_age_s = max_age_s
        self._cache = {}   # item_id -> (fetched_at, candles)

    def get(self, item_id, now):
        entry = self._cache.get(item_id)
        if entry is not None and (now - entry[0]) < self.max_age_s:
            return entry[1]
        candles = self.client.timeseries(item_id, self.timestep)
        self._cache[item_id] = (now, candles)
        return candles


def build_market_data(conn, mapping, history_cache, item_ids, now):
    """One MarketData per item that has a price_cache row. Skips items without
    current prices."""
    markets = []
    for item_id in item_ids:
        row = conn.execute(
            "SELECT * FROM price_cache WHERE item_id=?", (item_id,)).fetchone()
        if row is None:
            continue
        meta = mapping.get(str(item_id), {})
        markets.append(MarketData(
            item_id=item_id,
            name=meta.get("name", str(item_id)),
            low=row["low"],
            high=row["high"],
            vol_1h=row["vol_1h"],
            history=history_cache.get(item_id, now=now),
            buy_limit=meta.get("limit", 0) or 0,
            members=bool(meta.get("members", False)),
        ))
    return markets
```

- [ ] **Step 4: Run, verify pass**

Run: `python -m pytest tests/test_market.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add bot/market.py tests/test_market.py
git commit -m "feat: add market assembly and position adapter"
```

---

### Task 3: Live evaluation

**Files:**
- Create: `bot/engine_live.py`
- Test: `tests/test_engine_live.py`

`evaluate` runs every RUNNING strategy_run's `find_buys` within `runs.available`, creates proposed positions (skipping items that already have an open position for that run), and for each FILLED position raises `high_water`, then inserts a sell `signals` row when the strategy says sell (de-duplicated). Strategies are instantiated per run via the loader using the run's stored params.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_engine_live.py
import json
from bot import db, runs, positions as pos
from bot.engine_live import evaluate
from bot.strategies.base import MarketData, BuySignal, SellDecision


def fresh():
    conn = db.connect(":memory:")
    db.init_db(conn)
    return conn


class AlwaysBuy:
    name = "alwaysbuy"
    def __init__(self, **p): self.params = p
    def find_buys(self, markets, budget):
        out = []
        for m in markets:
            if budget >= m.low:
                out.append(BuySignal(item_id=m.item_id, price=m.low, qty=1, reason="x"))
                budget -= m.low
        return out
    def should_sell(self, position, market):
        return SellDecision(sell=market.high >= 200, reason="hit")


def loader_stub(_dir):
    return {"alwaysbuy": AlwaysBuy()}


def market(item_id, low, high):
    return MarketData(item_id=item_id, name=f"i{item_id}", low=low, high=high,
                      vol_1h=1000, history=[], buy_limit=1000)


def test_creates_proposals_within_budget():
    conn = fresh()
    rid = runs.start_run(conn, "alwaysbuy", budget_gp=250)
    markets = {1: market(1, 100, 150), 2: market(2, 100, 150)}
    evaluate(conn, markets, now=0.0, loader=loader_stub)
    proposed = pos.list_positions(conn, state="proposed")
    assert len(proposed) == 2
    assert all(p["run_id"] == rid for p in proposed)


def test_skips_duplicate_open_position():
    conn = fresh()
    rid = runs.start_run(conn, "alwaysbuy", budget_gp=10_000)
    markets = {1: market(1, 100, 150)}
    evaluate(conn, markets, now=0.0, loader=loader_stub)
    evaluate(conn, markets, now=0.0, loader=loader_stub)   # second pass
    assert len(pos.list_positions(conn, state="proposed")) == 1


def test_stopped_run_produces_nothing():
    conn = fresh()
    rid = runs.start_run(conn, "alwaysbuy", budget_gp=10_000)
    runs.stop_run(conn, rid)
    evaluate(conn, {1: market(1, 100, 150)}, now=0.0, loader=loader_stub)
    assert pos.list_positions(conn) == []


def test_sell_recommendation_for_filled():
    conn = fresh()
    rid = runs.start_run(conn, "alwaysbuy", budget_gp=10_000)
    pid = pos.create_proposed(conn, strategy="alwaysbuy", item_id=1, item_name="i1",
                              buy_price=100, qty=1, run_id=rid)
    pos.accept(conn, pid); pos.mark_filled(conn, pid)
    evaluate(conn, {1: market(1, 180, 220)}, now=0.0, loader=loader_stub)  # high>=200
    sigs = conn.execute("SELECT * FROM signals WHERE type='sell'").fetchall()
    assert len(sigs) == 1 and sigs[0]["item_id"] == 1
    # idempotent: a second pass does not duplicate the sell signal
    evaluate(conn, {1: market(1, 180, 220)}, now=0.0, loader=loader_stub)
    assert len(conn.execute("SELECT * FROM signals WHERE type='sell'").fetchall()) == 1


def test_high_water_raised_for_filled():
    conn = fresh()
    rid = runs.start_run(conn, "alwaysbuy", budget_gp=10_000)
    pid = pos.create_proposed(conn, strategy="alwaysbuy", item_id=1, item_name="i1",
                              buy_price=100, qty=1, run_id=rid)
    pos.accept(conn, pid); pos.mark_filled(conn, pid)
    evaluate(conn, {1: market(1, 150, 190)}, now=0.0, loader=loader_stub)
    assert pos.get(conn, pid)["high_water"] == 190
```

- [ ] **Step 2: Run, verify failure**

Run: `python -m pytest tests/test_engine_live.py -v`
Expected: FAIL — no module `bot.engine_live`.

- [ ] **Step 3: Implement engine_live.py**

```python
# bot/engine_live.py
"""Live decision pass: turn running strategies + market data into proposed
positions and sell recommendations."""

import json
import os
from datetime import datetime, timezone

from bot import runs as runs_mod
from bot import positions as pos_mod
from bot.market import position_view
from bot.strategies.loader import load_strategies

_OPEN_STATES = ("proposed", "accepted", "filled", "selling")
_STRATEGIES_DIR = os.path.join(os.path.dirname(__file__), "strategies")


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _make_strategy(name, params, loader):
    found = loader(_STRATEGIES_DIR)
    proto = found.get(name)
    if proto is None:
        return None
    # rebuild with the run's params if the class supports it
    try:
        return type(proto)(**params)
    except TypeError:
        return proto


def _has_open_position(conn, run_id, item_id):
    row = conn.execute(
        "SELECT 1 FROM positions WHERE run_id=? AND item_id=? "
        f"AND state IN ({','.join('?' * len(_OPEN_STATES))}) LIMIT 1",
        (run_id, item_id, *_OPEN_STATES)).fetchone()
    return row is not None


def evaluate(conn, markets, now, loader=load_strategies):
    """markets: {item_id: MarketData}. Creates buy proposals for running runs
    and sell-recommendation signals for filled positions."""
    market_list = list(markets.values())

    # --- buys, per running run ---
    for run in runs_mod.list_runs(conn, state="running"):
        params = json.loads(run["params_json"] or "{}")
        strat = _make_strategy(run["strategy"], params, loader)
        if strat is None:
            continue
        budget = runs_mod.available(conn, run["id"])
        for sig in strat.find_buys(market_list, budget):
            if _has_open_position(conn, run["id"], sig.item_id):
                continue
            m = markets.get(sig.item_id)
            name = m.name if m else str(sig.item_id)
            pos_mod.create_proposed(
                conn, strategy=run["strategy"], item_id=sig.item_id,
                item_name=name, buy_price=sig.price, qty=sig.qty,
                run_id=run["id"])

    # --- sell recommendations, per filled position ---
    for p in pos_mod.list_positions(conn, state="filled"):
        m = markets.get(p["item_id"])
        if m is None:
            continue
        pos_mod.update_high_water(conn, p["id"], m.high)
        strat = _make_strategy(p["strategy"], {}, loader)
        if strat is None:
            continue
        view = position_view(pos_mod.get(conn, p["id"]))
        decision = strat.should_sell(view, m)
        if not decision.sell:
            continue
        exists = conn.execute(
            "SELECT 1 FROM signals WHERE item_id=? AND strategy=? AND type='sell' "
            "AND status='shown' LIMIT 1", (p["item_id"], p["strategy"])).fetchone()
        if exists:
            continue
        conn.execute(
            "INSERT INTO signals(item_id, strategy, type, price, reason, "
            "created_at, status) VALUES(?, ?, 'sell', ?, ?, ?, 'shown')",
            (p["item_id"], p["strategy"], m.high, decision.reason, _now_iso()))
        conn.commit()
```

- [ ] **Step 4: Run, verify pass**

Run: `python -m pytest tests/test_engine_live.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add bot/engine_live.py tests/test_engine_live.py
git commit -m "feat: add live evaluation engine"
```

---

### Task 4: Scheduler + main entry

**Files:**
- Create: `bot/scheduler.py`
- Create: `bot/main.py`
- Test: `tests/test_scheduler.py`

`PollScheduler` runs `poll_once` + `evaluate` on a daemon thread with ITS OWN db connection (never the API's — sqlite connections are not safe to share across threads). The watchlist + mapping are loaded once at start. `tick()` is the single cycle, tested directly without threads.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scheduler.py
from bot import db, runs, positions as pos
from bot.scheduler import PollScheduler
from bot.strategies.base import BuySignal, SellDecision


class StubClient:
    def latest(self):
        return {"1": {"high": 150, "low": 100}}
    def one_hour(self):
        return {"1": {"highPriceVolume": 500, "lowPriceVolume": 500}}
    def timeseries(self, item_id, timestep):
        return []
    def mapping(self):
        return [{"id": 1, "name": "Item1", "limit": 1000, "members": False}]


class AlwaysBuy:
    name = "alwaysbuy"
    def __init__(self, **p): self.params = p
    def find_buys(self, markets, budget):
        return [BuySignal(item_id=m.item_id, price=m.low, qty=1, reason="x")
                for m in markets if budget >= m.low]
    def should_sell(self, position, market):
        return SellDecision(sell=False, reason="")


def loader_stub(_dir):
    return {"alwaysbuy": AlwaysBuy()}


def test_tick_polls_then_proposes():
    conn = db.connect(":memory:")
    db.init_db(conn)
    runs.start_run(conn, "alwaysbuy", budget_gp=10_000)
    sched = PollScheduler(conn, StubClient(), watchlist=[1], loader=loader_stub)
    sched.tick(now=0.0)
    # price_cache populated by poll, and a proposal created by evaluate
    assert conn.execute("SELECT COUNT(*) c FROM price_cache").fetchone()["c"] == 1
    assert len(pos.list_positions(conn, state="proposed")) == 1
```

- [ ] **Step 2: Run, verify failure**

Run: `python -m pytest tests/test_scheduler.py -v`
Expected: FAIL — no module `bot.scheduler`.

- [ ] **Step 3: Implement scheduler.py**

```python
# bot/scheduler.py
"""Background poll+evaluate scheduler. Owns its own db connection."""

import threading
import time

from bot.poller import poll_once
from bot.engine_live import evaluate
from bot.strategies.loader import load_strategies


class PollScheduler:
    def __init__(self, conn, client, watchlist, interval_s=300,
                 timestep="24h", loader=load_strategies):
        self.conn = conn
        self.client = client
        self.watchlist = watchlist
        self.interval_s = interval_s
        self.timestep = timestep
        self.loader = loader
        self._mapping = None
        self._history = None
        self._stop = threading.Event()
        self._thread = None

    def _ensure_context(self):
        from bot.market import HistoryCache
        if self._mapping is None:
            self._mapping = {str(m["id"]): m for m in self.client.mapping()}
        if self._history is None:
            self._history = HistoryCache(self.client, timestep=self.timestep)

    def tick(self, now=None):
        now = time.monotonic() if now is None else now
        self._ensure_context()
        poll_once(self.client, self.conn)
        from bot.market import build_market_data
        markets = build_market_data(self.conn, self._mapping, self._history,
                                    self.watchlist, now=now)
        evaluate(self.conn, {m.item_id: m for m in markets}, now=now,
                 loader=self.loader)

    def _loop(self):
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                pass  # a poll failure must not kill the loop
            self._stop.wait(self.interval_s)

    def start(self):
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
```

- [ ] **Step 4: Create main.py**

```python
# bot/main.py
"""Entry point: open db, start the poll scheduler on its own connection, and
serve the FastAPI app. The API and the scheduler use SEPARATE connections."""

import os

import uvicorn

from bot import db
from bot.api_client import WikiClient
from bot.scheduler import PollScheduler
from bot.web import create_app

DB_PATH = os.environ.get("OSRS_BOT_DB", "osrs_bot.db")
USER_AGENT = os.environ.get(
    "OSRS_BOT_UA", "osrs-flip-bot/1.0 (contact: set OSRS_BOT_UA)")
# Default watchlist; replace/extend via config later.
WATCHLIST = [4151, 11802, 11832, 4712, 11785]


def build():
    api_conn = db.connect(DB_PATH)
    db.init_db(api_conn)
    client = WikiClient(user_agent=USER_AGENT)

    sched_conn = db.connect(DB_PATH)   # separate connection for the thread
    scheduler = PollScheduler(sched_conn, client, watchlist=WATCHLIST)

    app = create_app(api_conn)
    return app, scheduler


def main():
    app, scheduler = build()
    scheduler.start()
    try:
        uvicorn.run(app, host="127.0.0.1", port=8000)
    finally:
        scheduler.stop()


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run scheduler test + full suite**

Run: `python -m pytest tests/test_scheduler.py -v`
Expected: PASS (1 passed).
Run: `python -m pytest`
Expected: PASS — all phases green.

- [ ] **Step 6: Commit**

```bash
git add bot/scheduler.py bot/main.py tests/test_scheduler.py
git commit -m "feat: add poll scheduler and main entry point"
```

---

## Self-Review Notes

- **Spec coverage:** MarketData assembled from price_cache + mapping + cached `/timeseries` (market.py); running runs generate proposals within `runs.available` budget (engine_live, dedup via open-position check); filled positions get sell recommendations + high_water maintenance (engine_live); 5-min scheduler on a daemon thread (scheduler.py); main wires API + scheduler with SEPARATE db connections (thread safety — the Phase 4a review flag).
- **Type consistency:** strategies receive `MarketData` (attribute access) and a `position_view` SimpleNamespace (attribute access) — never a raw Row. `create_proposed(..., ref_price=None)` matches the Task 1 signature. `evaluate(conn, markets, now, loader=...)` identical in engine_live, its tests, and scheduler. `PollScheduler.tick(now=...)` matches its test.
- **Placeholder scan:** complete code + expected output in every step.
- **Known approximation:** the live `should_sell` for a `filled` position is instantiated with empty params (`{}`) — defaults. A future refinement can thread the originating run's params onto the position. Documented, not blocking.

## Next
Phase 5 — dashboard (the dark+gold UI from the mockup, wired to this API). Phase 6 — launcher + notifications.
