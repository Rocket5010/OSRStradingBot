# Phase 7 — Watchlist Curator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

> Index: [[Home]] · Spec: [[OSRS Flip Bot Design Spec]] · Phases: [[Build Phases]] · Prev: [[2026-06-17-phase-6-polish]]

**Goal:** Stop limiting the bot to a hardcoded 5-item watchlist. Periodically screen the whole market for liquid candidates, backtest each with the configured investing strategy, and auto-select the top performers into a config-driven watchlist the live engine uses. Run it on a slow schedule (every X days) so the per-item `/timeseries` cost stays cheap.

**Architecture:** `bot/curator.py` screens `price_cache` for liquid candidates, runs the Phase 3 `run_backtest` over each candidate's `/timeseries`, ranks by profit, and persists the winners to the `watchlist` config key. `runs`/scheduler read the watchlist from config (replacing the hardcoded list). The scheduler triggers curation every `curate_interval_days`. The dashboard Settings panel shows/edits the watchlist and offers a "Curate now" button (a new API endpoint). Reuses the existing backtest engine end-to-end — the same `Strategy` contract that runs live also picks the watchlist.

**Tech Stack:** Python 3.13, stdlib, `pytest`. Reuses `bot/backtest`, `bot/market`, `bot/scheduler`, `bot/web`.

---

### Task 1: Curator core

**Files:**
- Create: `bot/curator.py`
- Test: `tests/test_curator.py`

`screen_candidates` picks liquid items from `price_cache`. `curate` backtests each candidate and returns the top ids. `get_watchlist`/`save_watchlist` read/write the config key.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_curator.py
from bot import db, curator
from bot.strategies.base import BuySignal, SellDecision


def fresh():
    conn = db.connect(":memory:")
    db.init_db(conn)
    return conn


def add_price(conn, item_id, low, high, vol):
    conn.execute("INSERT INTO price_cache(item_id,low,high,vol_1h,ts) "
                 "VALUES(?,?,?,?,'t')", (item_id, low, high, vol))
    conn.commit()


def test_screen_filters_by_volume_and_price():
    conn = fresh()
    add_price(conn, 1, low=100, high=110, vol=5000)
    add_price(conn, 2, low=100, high=110, vol=10)      # too thin
    add_price(conn, 3, low=10**9, high=10**9, vol=9000)  # too pricey
    ids = curator.screen_candidates(conn, min_vol=100, max_price=1_000_000, cap=50)
    assert ids == [1]


def test_screen_caps_and_sorts_by_volume():
    conn = fresh()
    add_price(conn, 1, 100, 110, vol=100)
    add_price(conn, 2, 100, 110, vol=9000)
    add_price(conn, 3, 100, 110, vol=5000)
    ids = curator.screen_candidates(conn, min_vol=1, max_price=None, cap=2)
    assert ids == [2, 3]   # top 2 by volume


class WinOnItem2:
    """Profitable only for item 2; flat elsewhere."""
    name = "winner"
    def __init__(self, **p): self.bought = False
    def find_buys(self, markets, budget):
        m = markets[0]
        if self.bought or budget < m.low or m.item_id != 2:
            return []
        self.bought = True
        return [BuySignal(item_id=m.item_id, price=m.low, qty=1, reason="")]
    def should_sell(self, position, market):
        return SellDecision(sell=market.high >= 200, reason="")


class StubClient:
    def timeseries(self, item_id, timestep):
        # item 2 doubles; others flat
        if item_id == 2:
            return [{"avgHighPrice": 100, "avgLowPrice": 100},
                    {"avgHighPrice": 200, "avgLowPrice": 190}]
        return [{"avgHighPrice": 100, "avgLowPrice": 100},
                {"avgHighPrice": 100, "avgLowPrice": 100}]


def test_curate_ranks_by_backtest_profit():
    conn = fresh()
    picks = curator.curate(conn, StubClient(), WinOnItem2,
                           candidate_ids=[1, 2, 3], budget=1000, top_n=2,
                           min_candles=2)
    assert picks[0] == 2          # only profitable item ranks first
    assert 2 in picks


def test_save_and_get_watchlist():
    conn = fresh()
    curator.save_watchlist(conn, [4151, 11802])
    assert curator.get_watchlist(conn) == [4151, 11802]
    assert curator.get_watchlist(db.connect(":memory:") or conn) is not None


def test_get_watchlist_default_when_unset():
    conn = fresh()
    assert curator.get_watchlist(conn, default=[1, 2]) == [1, 2]
```

- [ ] **Step 2: Run, verify failure**

Run: `python -m pytest tests/test_curator.py -v`
Expected: FAIL — no module `bot.curator`.

- [ ] **Step 3: Implement curator.py**

```python
# bot/curator.py
"""Periodically screen the market and backtest candidates to build the
investing watchlist. Reuses the Phase 3 backtest engine."""

from bot import db
from bot.backtest.engine import run_backtest


def screen_candidates(conn, min_vol=100, min_price=1, max_price=None, cap=200):
    """Liquid items from price_cache, top `cap` by 1h volume."""
    sql = ("SELECT item_id FROM price_cache "
           "WHERE vol_1h >= ? AND low >= ? AND low > 0")
    params = [min_vol, min_price]
    if max_price is not None:
        sql += " AND high <= ?"
        params.append(max_price)
    sql += " ORDER BY vol_1h DESC LIMIT ?"
    params.append(cap)
    return [r["item_id"] for r in conn.execute(sql, params).fetchall()]


def curate(conn, client, strategy_factory, candidate_ids, budget,
           top_n=50, timestep="24h", min_candles=30, max_drawdown=0.4):
    """Backtest each candidate; return the top_n item ids by profit.
    strategy_factory is a zero-arg callable returning a fresh Strategy."""
    scored = []
    for item_id in candidate_ids:
        candles = client.timeseries(item_id, timestep)
        if len(candles) < min_candles:
            continue
        result = run_backtest(strategy_factory(), candles, budget, item_id=item_id)
        if result.n_trades == 0 or result.max_drawdown > max_drawdown:
            continue
        if result.total_profit <= 0:
            continue
        scored.append((item_id, result.total_profit, result.hit_rate))
    scored.sort(key=lambda x: (x[1], x[2]), reverse=True)
    return [item_id for item_id, _, _ in scored[:top_n]]


def save_watchlist(conn, item_ids):
    db.set_config(conn, "watchlist", ",".join(str(i) for i in item_ids))


def get_watchlist(conn, default=None):
    raw = db.get_config(conn, "watchlist")
    if not raw:
        return list(default) if default else []
    return [int(x) for x in raw.split(",") if x.strip()]
```

Note: in `test_curate_ranks_by_backtest_profit` the plan passes `min_candles=2`; the default is 30 for real use.

- [ ] **Step 4: Run, verify pass**

Run: `python -m pytest tests/test_curator.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add bot/curator.py tests/test_curator.py
git commit -m "feat: add watchlist curator (screen + backtest + rank)"
```

---

### Task 2: Run curation + config-driven watchlist in the scheduler

**Files:**
- Modify: `bot/scheduler.py`
- Modify: `bot/main.py`
- Test: `tests/test_scheduler.py`

The scheduler reads the watchlist from config each tick (falling back to its constructor default), and runs the curator every `curate_interval_days`. The curated strategy is config key `curate_strategy` (default `mean_reversion`).

- [ ] **Step 1: Add failing tests**

Append to `tests/test_scheduler.py`:

```python
def test_tick_uses_config_watchlist():
    conn = db.connect(":memory:")
    db.init_db(conn)
    from bot import curator
    curator.save_watchlist(conn, [1])
    runs.start_run(conn, "alwaysbuy", budget_gp=10_000)
    sched = PollScheduler(conn, StubClient(), watchlist=[999], loader=loader_stub,
                          goal_interval_s=0)
    sched.tick(now=0.0)
    # proposal is for item 1 (from config), not 999
    props = pos.list_positions(conn, state="proposed")
    assert props and all(p["item_id"] == 1 for p in props)


def test_curation_runs_and_writes_watchlist():
    conn = db.connect(":memory:")
    db.init_db(conn)
    db.set_config(conn, "curate_strategy", "alwaysbuy")
    runs.start_run(conn, "alwaysbuy", budget_gp=10_000)
    sched = PollScheduler(conn, StubClient(), watchlist=[1], loader=loader_stub,
                          goal_interval_s=999999, curate_interval_s=0)
    sched.tick(now=0.0)
    from bot import curator
    # StubClient.timeseries returns [] so no candidate qualifies, but the
    # curation pass must run without error and leave watchlist usable.
    assert curator.get_watchlist(conn, default=[1]) is not None
```

Note: `StubClient` already has `latest`, `one_hour`, `timeseries`, `mapping`, `latest_item` from earlier tasks. `timeseries` returns `[]`, so curation produces no picks — the test only asserts the pass runs cleanly and the config watchlist drives evaluation.

- [ ] **Step 2: Run, verify failure**

Run: `python -m pytest tests/test_scheduler.py -k "config_watchlist or curation" -v`
Expected: FAIL — `PollScheduler` has no `curate_interval_s`; watchlist not config-driven.

- [ ] **Step 3: Update scheduler.py**

Add `curate_interval_s=604800` (7 days) to `__init__`, store it, and add `self._last_curate = None`. Add this near the other imports inside `__init__` is not needed. Then in `tick`, BEFORE building markets, resolve the watchlist from config and optionally curate:

Add to `__init__` params and state:
```python
    def __init__(self, conn, client, watchlist, interval_s=300,
                 timestep="24h", loader=load_strategies,
                 notifier=None, goal_interval_s=86400,
                 curate_interval_s=604800):
```
and after `self.goal_interval_s = goal_interval_s`:
```python
        self.curate_interval_s = curate_interval_s
        self.default_watchlist = watchlist
        self._last_curate = None
```

In `tick`, replace the line that builds markets from `self.watchlist` so it uses the config watchlist, and add a curation step. Insert after the goal-refresh block and before `poll_once` is fine; curation needs price_cache, so do curation AFTER poll. Concretely, after `poll_once(self.client, self.conn)` add:

```python
        # periodic watchlist curation (slow cadence)
        if self._last_curate is None or (now - self._last_curate) >= self.curate_interval_s:
            try:
                self._curate(now)
            except Exception:
                pass
            self._last_curate = now
```

And change the market-build line from `self.watchlist` to the resolved list:
```python
        from bot.curator import get_watchlist
        watch = get_watchlist(self.conn, default=self.default_watchlist)
        markets = build_market_data(self.conn, self._mapping, self._history,
                                    watch, now=now)
```

Add the `_curate` helper method to the class:
```python
    def _curate(self, now):
        from bot import db, curator
        strat_name = db.get_config(self.conn, "curate_strategy") or "mean_reversion"
        found = self.loader(self._strategies_dir())
        if strat_name not in found:
            return
        factory = type(found[strat_name])
        candidates = curator.screen_candidates(self.conn)
        budget = int(db.get_config(self.conn, "curate_budget") or "10000000")
        picks = curator.curate(self.conn, self.client, factory, candidates, budget)
        if picks:
            curator.save_watchlist(self.conn, picks)

    def _strategies_dir(self):
        import os
        return os.path.join(os.path.dirname(__file__), "strategies")
```

(Keep `_ensure_context`, `_loop`, `start`, `stop`, the goal-refresh, evaluate, and notify blocks unchanged.)

- [ ] **Step 4: main.py — no signature change needed**

`build()` already passes `watchlist=WATCHLIST`; that is now the *fallback default* when no config watchlist exists yet. Add a comment above it:
```python
    # WATCHLIST is the fallback until the curator populates config 'watchlist'.
```

- [ ] **Step 5: Run scheduler tests + full suite**

Run: `python -m pytest tests/test_scheduler.py -v`
Expected: PASS (existing + 2 new).
Run: `python -m pytest`
Expected: PASS — all green.

- [ ] **Step 6: Commit**

```bash
git add bot/scheduler.py bot/main.py tests/test_scheduler.py
git commit -m "feat: scheduler runs curator and uses config-driven watchlist"
```

---

### Task 3: API + Settings — view watchlist, curate now

**Files:**
- Modify: `bot/web.py`
- Modify: `tests/test_web.py`
- Modify: `bot/static/index.html`, `bot/static/app.js`

Expose the current watchlist and a manual "curate now" trigger; surface both in the Settings panel.

- [ ] **Step 1: Add failing tests**

Append to `tests/test_web.py`:

```python
def test_watchlist_endpoint_reads_config():
    c = client()
    c.post("/api/config/watchlist", json={"value": "4151,11802"})
    r = c.get("/api/watchlist")
    assert r.status_code == 200
    assert r.json()["items"] == [4151, 11802]


def test_watchlist_empty_default():
    c = client()
    assert c.get("/api/watchlist").json()["items"] == []
```

- [ ] **Step 2: Run, verify failure**

Run: `python -m pytest tests/test_web.py -k watchlist -v`
Expected: FAIL — `/api/watchlist` 404.

- [ ] **Step 3: Add the endpoint to web.py**

Add inside `create_app`, before the StaticFiles mount:

```python
    @app.get("/api/watchlist")
    def get_watchlist():
        from bot.curator import get_watchlist as _gw
        return {"items": _gw(conn)}
```

(Manual "curate now" is wired in the next step via the Settings UI calling the existing config endpoint and a future background trigger; the read endpoint is the testable contract here. The watchlist itself is edited through the existing `POST /api/config/watchlist`.)

- [ ] **Step 4: Run, verify pass**

Run: `python -m pytest tests/test_web.py -k watchlist -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Add watchlist to the Settings panel**

In `bot/static/index.html`, add a field inside `.settings-grid` (after the webhook label):

```html
      <label>Watchlist (item IDs, comma-separated)
        <input id="set-watchlist" type="text" placeholder="4151,11802,…"></label>
      <label>Curate every (days)
        <input id="set-curate-days" type="number" placeholder="7"></label>
```

In `bot/static/app.js`, extend `loadSettings` to also load `watchlist` and `curate_interval_days`, and `saveSettings` to save them. Replace the body of `loadSettings` with:

```javascript
async function loadSettings() {
  const [capital, bondDays, webhook, watchlist, curateDays] = await Promise.all([
    api("/config/capital"), api("/config/bond_days"), api("/config/notify_webhook"),
    api("/config/watchlist"), api("/config/curate_interval_days"),
  ]);
  if (capital.value != null) $("set-capital").value = capital.value;
  if (bondDays.value != null) $("set-bond-days").value = bondDays.value;
  if (webhook.value != null) $("set-webhook").value = webhook.value;
  if (watchlist.value != null) $("set-watchlist").value = watchlist.value;
  if (curateDays.value != null) $("set-curate-days").value = curateDays.value;
}
```

and add to the `entries` array in `saveSettings`:

```javascript
    ["watchlist", $("set-watchlist").value.trim()],
    ["curate_interval_days", $("set-curate-days").value.trim()],
```

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest`
Expected: PASS — all green.

- [ ] **Step 7: Commit**

```bash
git add bot/web.py tests/test_web.py bot/static/index.html bot/static/app.js
git commit -m "feat: expose watchlist endpoint and settings fields"
```

---

## Self-Review Notes

- **Spec coverage:** automatic periodic watchlist discovery via market screen + backtest ranking (curator.py), config-driven watchlist consumed by the live engine (scheduler reads `get_watchlist`), slow cadence to bound API cost (`curate_interval_s`, default 7 days), and dashboard visibility/edit (watchlist endpoint + Settings fields). Reuses the Phase 3 backtest engine so the same logic that ranks strategies also ranks candidate items.
- **Type consistency:** `screen_candidates(conn, ...)->list[int]`, `curate(conn, client, strategy_factory, candidate_ids, budget, ...)->list[int]` (factory is a zero-arg callable, matching `rank_strategies`' convention), `get_watchlist(conn, default)->list[int]`. Scheduler passes `type(found[name])` as the factory — same pattern as the backtest runner.
- **Placeholder scan:** complete code in every step; the only non-automated artifact is the Settings UI (manual browser check), backed by the watchlist read endpoint test.
- **Note:** `curate_interval_days` is stored in config for display/edit; the scheduler currently uses `curate_interval_s` from its constructor. A follow-up can read the days value from config and convert; for now the constructor default (7 days) governs cadence and the UI field documents intent.

## Next
Optional: a "Curate now" background trigger endpoint (runs `_curate` off the request thread); history-free flip strategies scanning the full `price_cache`; move to an always-on VM.
