# Phase 4a — API & State Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> Index: [[Home]] · Spec: [[OSRS Flip Bot Design Spec]] · Phases: [[Build Phases]] · Prev: [[2026-06-16-phase-3-backtest]]

**Goal:** Build the stateful core and JSON API — manage strategy runs (manual start + per-run gp budget), drive the position lifecycle (accept/fill/sell/cancel/dismiss with P/L), and expose it all over a FastAPI app the dashboard will consume. (The live decision engine that auto-generates proposals is Phase 4b.)

**Architecture:** `bot/runs.py` manages `strategy_runs` (start/stop, budget, spent tracking). `bot/positions.py` manages the `positions` lifecycle and computes realized P/L on close, updating run `spent_gp` as capital is committed/released. `bot/web.py` exposes a `create_app(conn)` FastAPI factory with REST endpoints for strategies, runs, positions, and config — pure presentation-agnostic JSON. All modules take a sqlite connection, so tests use an in-memory DB and FastAPI's `TestClient`.

**Tech Stack:** Python 3.13, `fastapi`, `uvicorn`, `pydantic` (bundled), `httpx` (TestClient), stdlib `sqlite3`, `pytest`.

---

## File Structure

```
bot/
├── runs.py            # strategy_runs management
├── positions.py       # position lifecycle + P/L
└── web.py             # create_app(conn) FastAPI factory
tests/
├── test_runs.py
├── test_positions.py
└── test_web.py
requirements.txt       # runtime deps
```

## Position lifecycle (recap from [[Position Lifecycle]])

```
proposed ──accept──▶ accepted ──fill──▶ filled ──sell──▶ selling ──sold──▶ sold
   │                    │                                   │
   └──dismiss─▶dismissed └──cancel─▶cancelled    cancel─────┘
```
Capital is committed to the run's `spent_gp` on **accept** and released on **sold** or **cancel**.

---

### Task 1: Record runtime dependencies

**Files:**
- Create: `requirements.txt`

- [ ] **Step 1: Create requirements.txt**

```
fastapi
uvicorn
httpx
```

- [ ] **Step 2: Commit**

```bash
git add requirements.txt
git commit -m "chore: record runtime dependencies"
```

---

### Task 2: Strategy run management

**Files:**
- Create: `bot/runs.py`
- Test: `tests/test_runs.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_runs.py
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
```

- [ ] **Step 2: Run, verify failure**

Run: `python -m pytest tests/test_runs.py -v`
Expected: FAIL — no module `bot.runs`.

- [ ] **Step 3: Implement runs.py**

```python
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


def available(conn, run_id):
    r = get_run(conn, run_id)
    return r["budget_gp"] - r["spent_gp"] if r else 0
```

- [ ] **Step 4: Run, verify pass**

Run: `python -m pytest tests/test_runs.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add bot/runs.py tests/test_runs.py
git commit -m "feat: add strategy run management"
```

---

### Task 3: Position lifecycle

**Files:**
- Create: `bot/positions.py`
- Test: `tests/test_positions.py`

Each transition validates the current state and raises `ValueError` on an illegal move. `accept` commits capital to the run; `mark_sold`/`cancel` release it. P/L on sale uses the shared `ge_tax`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_positions.py
import pytest
from bot import db, runs, positions as pos


def fresh():
    conn = db.connect(":memory:")
    db.init_db(conn)
    return conn


def make(conn, run_id=None, buy_price=100, qty=10):
    return pos.create_proposed(conn, strategy="rsi", item_id=2, item_name="Cb",
                               buy_price=buy_price, qty=qty, run_id=run_id,
                               sell_target=120, stop_loss=90)


def test_create_is_proposed():
    conn = fresh()
    pid = make(conn)
    assert pos.get(conn, pid)["state"] == "proposed"


def test_happy_path_to_sold_computes_pl():
    conn = fresh()
    rid = runs.start_run(conn, "rsi", budget_gp=10_000)
    pid = make(conn, run_id=rid, buy_price=100, qty=10)
    pos.accept(conn, pid)
    assert runs.available(conn, rid) == 10_000 - 1000   # committed
    pos.mark_filled(conn, pid)
    pos.start_selling(conn, pid)
    pl = pos.mark_sold(conn, pid, sell_price=120)
    # proceeds = (120 - floor(120*0.02)=2) * 10 = 1180; cost 1000 -> pl 180
    assert pl == 180
    row = pos.get(conn, pid)
    assert row["state"] == "sold" and row["realized_pl"] == 180
    assert runs.available(conn, rid) == 10_000   # capital released


def test_dismiss_from_proposed():
    conn = fresh()
    pid = make(conn)
    pos.dismiss(conn, pid)
    assert pos.get(conn, pid)["state"] == "dismissed"


def test_cancel_releases_capital():
    conn = fresh()
    rid = runs.start_run(conn, "rsi", budget_gp=10_000)
    pid = make(conn, run_id=rid, buy_price=100, qty=10)
    pos.accept(conn, pid)
    pos.cancel(conn, pid)
    assert pos.get(conn, pid)["state"] == "cancelled"
    assert runs.available(conn, rid) == 10_000


def test_illegal_transition_raises():
    conn = fresh()
    pid = make(conn)
    with pytest.raises(ValueError):
        pos.mark_sold(conn, pid, 120)   # cannot sell a proposed position


def test_list_filters_by_state():
    conn = fresh()
    a = make(conn)
    b = make(conn)
    pos.dismiss(conn, b)
    proposed = pos.list_positions(conn, state="proposed")
    assert {p["id"] for p in proposed} == {a}
```

- [ ] **Step 2: Run, verify failure**

Run: `python -m pytest tests/test_positions.py -v`
Expected: FAIL — no module `bot.positions`.

- [ ] **Step 3: Implement positions.py**

```python
# bot/positions.py
"""Position lifecycle: proposed -> accepted -> filled -> selling -> sold,
with dismiss/cancel branches. Commits/releases run capital and computes P/L."""

from datetime import datetime, timezone

from bot.tax import ge_tax
from bot import runs as runs_mod


def _now():
    return datetime.now(timezone.utc).isoformat()


def create_proposed(conn, strategy, item_id, item_name, buy_price, qty,
                    run_id=None, sell_target=None, stop_loss=None):
    cur = conn.execute(
        "INSERT INTO positions(item_id, item_name, strategy, run_id, state, "
        "buy_price, qty, sell_target, stop_loss, created_at) "
        "VALUES(?, ?, ?, ?, 'proposed', ?, ?, ?, ?, ?)",
        (item_id, item_name, strategy, run_id, buy_price, qty,
         sell_target, stop_loss, _now()),
    )
    conn.commit()
    return cur.lastrowid


def get(conn, pid):
    return conn.execute("SELECT * FROM positions WHERE id=?", (pid,)).fetchone()


def list_positions(conn, state=None):
    if state:
        return conn.execute(
            "SELECT * FROM positions WHERE state=? ORDER BY id", (state,)
        ).fetchall()
    return conn.execute("SELECT * FROM positions ORDER BY id").fetchall()


def _require(pos, *allowed):
    if pos["state"] not in allowed:
        raise ValueError(
            f"position {pos['id']} is '{pos['state']}', expected one of {allowed}")


def _committed(pos):
    return pos["buy_price"] * pos["qty"]


def accept(conn, pid):
    p = get(conn, pid)
    _require(p, "proposed")
    conn.execute("UPDATE positions SET state='accepted' WHERE id=?", (pid,))
    if p["run_id"]:
        runs_mod.add_spent(conn, p["run_id"], _committed(p))
    conn.commit()


def mark_filled(conn, pid):
    p = get(conn, pid)
    _require(p, "accepted")
    conn.execute("UPDATE positions SET state='filled', filled_at=? WHERE id=?",
                 (_now(), pid))
    conn.commit()


def start_selling(conn, pid):
    p = get(conn, pid)
    _require(p, "filled")
    conn.execute("UPDATE positions SET state='selling' WHERE id=?", (pid,))
    conn.commit()


def mark_sold(conn, pid, sell_price):
    p = get(conn, pid)
    _require(p, "selling")
    qty = p["qty"]
    pl = (sell_price - ge_tax(sell_price)) * qty - p["buy_price"] * qty
    conn.execute(
        "UPDATE positions SET state='sold', sell_price=?, realized_pl=?, "
        "closed_at=? WHERE id=?", (sell_price, pl, _now(), pid))
    if p["run_id"]:
        runs_mod.add_spent(conn, p["run_id"], -_committed(p))
    conn.commit()
    return pl


def cancel(conn, pid):
    p = get(conn, pid)
    _require(p, "accepted", "selling")
    conn.execute("UPDATE positions SET state='cancelled', closed_at=? WHERE id=?",
                 (_now(), pid))
    if p["run_id"]:
        runs_mod.add_spent(conn, p["run_id"], -_committed(p))
    conn.commit()


def dismiss(conn, pid):
    p = get(conn, pid)
    _require(p, "proposed")
    conn.execute("UPDATE positions SET state='dismissed', closed_at=? WHERE id=?",
                 (_now(), pid))
    conn.commit()
```

- [ ] **Step 4: Run, verify pass**

Run: `python -m pytest tests/test_positions.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add bot/positions.py tests/test_positions.py
git commit -m "feat: add position lifecycle with P/L and capital tracking"
```

---

### Task 4: FastAPI app — strategies, runs, config

**Files:**
- Create: `bot/web.py`
- Test: `tests/test_web.py`

`create_app(conn)` returns a FastAPI app closing over the connection. This task wires strategy listing, run endpoints, and config. Positions are added in Task 5.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_web.py
from fastapi.testclient import TestClient
from bot import db
from bot.web import create_app


def client():
    conn = db.connect(":memory:")
    db.init_db(conn)
    return TestClient(create_app(conn))


def test_list_strategies():
    c = client()
    r = c.get("/api/strategies")
    assert r.status_code == 200
    names = {s["name"] for s in r.json()}
    assert "mean_reversion" in names and "margin_flip" in names
    assert all("default_params" in s for s in r.json())


def test_start_and_list_run():
    c = client()
    r = c.post("/api/runs", json={"strategy": "rsi", "budget_gp": 5_000_000,
                                  "params": {"lo": 25}})
    assert r.status_code == 200
    run = r.json()
    assert run["state"] == "running" and run["budget_gp"] == 5_000_000
    listed = c.get("/api/runs").json()
    assert len(listed) == 1


def test_stop_run():
    c = client()
    rid = c.post("/api/runs", json={"strategy": "rsi", "budget_gp": 1}).json()["id"]
    r = c.post(f"/api/runs/{rid}/stop")
    assert r.status_code == 200 and r.json()["state"] == "stopped"


def test_stop_missing_run_404():
    c = client()
    assert c.post("/api/runs/999/stop").status_code == 404


def test_config_roundtrip():
    c = client()
    c.post("/api/config/capital", json={"value": "42000000"})
    assert c.get("/api/config/capital").json()["value"] == "42000000"
```

- [ ] **Step 2: Run, verify failure**

Run: `python -m pytest tests/test_web.py -v`
Expected: FAIL — no module `bot.web`.

- [ ] **Step 3: Implement web.py (strategies/runs/config)**

```python
# bot/web.py
"""FastAPI JSON API. create_app(conn) closes over a sqlite connection so
tests can pass an in-memory DB. Presentation-agnostic — returns plain JSON."""

import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from bot import db as db_mod
from bot import runs as runs_mod
from bot import positions as pos_mod
from bot.strategies.loader import load_strategies


def _row(r):
    return dict(r) if r is not None else None


class StartRunBody(BaseModel):
    strategy: str
    budget_gp: int
    params: dict = {}


class ConfigBody(BaseModel):
    value: str


class CreatePositionBody(BaseModel):
    strategy: str
    item_id: int
    item_name: str
    buy_price: int
    qty: int
    run_id: int | None = None
    sell_target: int | None = None
    stop_loss: int | None = None


class SellBody(BaseModel):
    sell_price: int


def create_app(conn, strategies_dir=None):
    app = FastAPI(title="OSRS Flip Bot")
    sdir = os.path.abspath(
        strategies_dir or os.path.join(os.path.dirname(__file__), "strategies"))

    @app.get("/api/strategies")
    def list_strategies():
        found = load_strategies(sdir)
        return [{"name": n, "description": s.description,
                 "default_params": s.default_params()}
                for n, s in found.items()]

    @app.get("/api/runs")
    def list_runs():
        return [_row(r) for r in runs_mod.list_runs(conn)]

    @app.post("/api/runs")
    def start_run(body: StartRunBody):
        rid = runs_mod.start_run(conn, body.strategy, body.budget_gp, body.params)
        return _row(runs_mod.get_run(conn, rid))

    @app.post("/api/runs/{run_id}/stop")
    def stop_run(run_id: int):
        if runs_mod.get_run(conn, run_id) is None:
            raise HTTPException(status_code=404, detail="run not found")
        runs_mod.stop_run(conn, run_id)
        return _row(runs_mod.get_run(conn, run_id))

    @app.get("/api/config/{key}")
    def get_config(key: str):
        return {"key": key, "value": db_mod.get_config(conn, key)}

    @app.post("/api/config/{key}")
    def set_config(key: str, body: ConfigBody):
        db_mod.set_config(conn, key, body.value)
        return {"key": key, "value": body.value}

    return app
```

- [ ] **Step 4: Run, verify pass**

Run: `python -m pytest tests/test_web.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add bot/web.py tests/test_web.py
git commit -m "feat: add FastAPI app with strategies, runs, config"
```

---

### Task 5: FastAPI app — position endpoints

**Files:**
- Modify: `bot/web.py`
- Modify: `tests/test_web.py`

Add position creation + lifecycle endpoints to the existing app. A `ValueError` from an illegal transition maps to HTTP 409; a missing position to 404.

- [ ] **Step 1: Add failing tests**

Append to `tests/test_web.py`:

```python
def _make_position(c, run_id=None):
    return c.post("/api/positions", json={
        "strategy": "rsi", "item_id": 2, "item_name": "Cb",
        "buy_price": 100, "qty": 10, "run_id": run_id,
        "sell_target": 120, "stop_loss": 90,
    }).json()


def test_create_and_list_position():
    c = client()
    p = _make_position(c)
    assert p["state"] == "proposed"
    listed = c.get("/api/positions?state=proposed").json()
    assert len(listed) == 1


def test_position_full_lifecycle():
    c = client()
    rid = c.post("/api/runs", json={"strategy": "rsi", "budget_gp": 10_000}).json()["id"]
    pid = _make_position(c, run_id=rid)["id"]
    assert c.post(f"/api/positions/{pid}/accept").json()["state"] == "accepted"
    assert c.post(f"/api/positions/{pid}/fill").json()["state"] == "filled"
    assert c.post(f"/api/positions/{pid}/sell").json()["state"] == "selling"
    sold = c.post(f"/api/positions/{pid}/sold", json={"sell_price": 120}).json()
    assert sold["state"] == "sold" and sold["realized_pl"] == 180


def test_illegal_transition_409():
    c = client()
    pid = _make_position(c)["id"]
    # cannot fill a proposed position (must accept first)
    assert c.post(f"/api/positions/{pid}/fill").status_code == 409


def test_missing_position_404():
    c = client()
    assert c.post("/api/positions/999/accept").status_code == 404


def test_dismiss_and_cancel():
    c = client()
    pid = _make_position(c)["id"]
    assert c.post(f"/api/positions/{pid}/dismiss").json()["state"] == "dismissed"
    pid2 = _make_position(c)["id"]
    c.post(f"/api/positions/{pid2}/accept")
    assert c.post(f"/api/positions/{pid2}/cancel").json()["state"] == "cancelled"
```

- [ ] **Step 2: Run, verify failure**

Run: `python -m pytest tests/test_web.py -v`
Expected: FAIL — `/api/positions` returns 404/405 (not yet defined).

- [ ] **Step 3: Add position endpoints to web.py**

Insert these routes inside `create_app`, before `return app` (after the config routes):

```python
    @app.get("/api/positions")
    def list_positions(state: str | None = None):
        return [_row(r) for r in pos_mod.list_positions(conn, state)]

    @app.post("/api/positions")
    def create_position(body: CreatePositionBody):
        pid = pos_mod.create_proposed(
            conn, strategy=body.strategy, item_id=body.item_id,
            item_name=body.item_name, buy_price=body.buy_price, qty=body.qty,
            run_id=body.run_id, sell_target=body.sell_target,
            stop_loss=body.stop_loss)
        return _row(pos_mod.get(conn, pid))

    def _transition(pid, fn, *args):
        if pos_mod.get(conn, pid) is None:
            raise HTTPException(status_code=404, detail="position not found")
        try:
            fn(conn, pid, *args)
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        return _row(pos_mod.get(conn, pid))

    @app.post("/api/positions/{pid}/accept")
    def accept_position(pid: int):
        return _transition(pid, pos_mod.accept)

    @app.post("/api/positions/{pid}/fill")
    def fill_position(pid: int):
        return _transition(pid, pos_mod.mark_filled)

    @app.post("/api/positions/{pid}/sell")
    def sell_position(pid: int):
        return _transition(pid, pos_mod.start_selling)

    @app.post("/api/positions/{pid}/sold")
    def sold_position(pid: int, body: SellBody):
        return _transition(pid, pos_mod.mark_sold, body.sell_price)

    @app.post("/api/positions/{pid}/cancel")
    def cancel_position(pid: int):
        return _transition(pid, pos_mod.cancel)

    @app.post("/api/positions/{pid}/dismiss")
    def dismiss_position(pid: int):
        return _transition(pid, pos_mod.dismiss)
```

- [ ] **Step 4: Run, verify pass**

Run: `python -m pytest tests/test_web.py -v`
Expected: PASS (10 passed).

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest`
Expected: PASS — all phases green.

- [ ] **Step 6: Commit**

```bash
git add bot/web.py tests/test_web.py
git commit -m "feat: add position endpoints to API"
```

---

## Self-Review Notes

- **Spec coverage:** manual strategy start + per-run budget (runs.py, POST /api/runs) ✓; position lifecycle with accept/fill/sell/cancel/dismiss + P/L (positions.py, position endpoints) ✓; capital committed/released against run `spent_gp` ✓; config kv for capital/bond settings ✓; JSON-only API decoupled from any frontend ✓. Live auto-proposal generation is deliberately Phase 4b.
- **Type consistency:** all modules take `conn` first. `create_proposed(conn, strategy, item_id, item_name, buy_price, qty, run_id, sell_target, stop_loss)` matches the API body and tests. `mark_sold(conn, pid, sell_price)` matches `_transition(pid, pos_mod.mark_sold, body.sell_price)`. Transition names (`accept`, `mark_filled`, `start_selling`, `mark_sold`, `cancel`, `dismiss`) used identically in positions.py and web.py.
- **Placeholder scan:** every code step complete; every run step has expected output.
- **Note for 4b:** the live engine will call `pos_mod.create_proposed(...)` to surface buy proposals and will call `strategy.should_sell` on `filled` positions to drive the "SELL NOW" recommendation; it reuses these exact functions — no API change needed.

## Next Phase
Phase 4b — live decision engine: assemble `MarketData` (price_cache + cached `/timeseries`), run each running strategy's `find_buys`/`should_sell` within its budget, persist proposals via `positions.create_proposed`, and schedule it on the poll loop.
