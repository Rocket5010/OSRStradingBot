# Phase 6 — Polish (Launcher, Notifications, Goal) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

> Index: [[Home]] · Spec: [[OSRS Flip Bot Design Spec]] · Phases: [[Build Phases]] · Prev: [[2026-06-17-phase-5-dashboard]]

**Goal:** Make the bot usable day-to-day: push notifications (Discord/Telegram-style webhook) when the bot proposes a buy or recommends a sell, keep the [[Bond Goal]] live (fetch bond price + manage the goal period), and launch the whole thing CMD-free with a one-click script.

**Architecture:** `bot/notify.py` posts a JSON webhook (works with Discord's `{content}` and any compatible endpoint), with the HTTP poster injectable for tests. `bot/goal.py` refreshes the bond price into `config` and initializes the goal period. The scheduler gains an injectable `notifier` and fires it for newly-created proposals / sell signals, plus a throttled goal refresh. A `start-bot.bat` launches the server hidden and opens the browser. See [[Launch]].

**Tech Stack:** Python 3.13, stdlib `urllib`, `pytest`. Windows `.bat` launcher.

---

### Task 1: Notifier

**Files:**
- Create: `bot/notify.py`
- Test: `tests/test_notify.py`

`notify(webhook_url, message, poster=post_json)` returns False when no URL is set (notifications optional), else posts `{"content": message}`. `format_buy`/`format_sell` build human messages.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_notify.py
from bot import notify


def test_notify_no_url_is_noop():
    calls = []
    assert notify.notify("", "hi", poster=lambda u, p: calls.append((u, p))) is False
    assert calls == []


def test_notify_posts_content():
    calls = []
    ok = notify.notify("http://hook", "hello", poster=lambda u, p: calls.append((u, p)))
    assert ok is True
    assert calls == [("http://hook", {"content": "hello"})]


def test_format_buy():
    msg = notify.format_buy("Abyssal whip", 1500000, 5, "below band")
    assert "Abyssal whip" in msg and "BUY" in msg.upper()


def test_format_sell():
    msg = notify.format_sell("Abyssal whip", 1700000, "reverted to mean")
    assert "Abyssal whip" in msg and "SELL" in msg.upper()
```

- [ ] **Step 2: Run, verify failure**

Run: `python -m pytest tests/test_notify.py -v`
Expected: FAIL — no module `bot.notify`.

- [ ] **Step 3: Implement notify.py**

```python
# bot/notify.py
"""Optional push notifications via a JSON webhook (Discord-compatible)."""

import json
import urllib.request


def post_json(url, payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status


def notify(webhook_url, message, poster=post_json):
    """Post a message to the webhook. Returns False if no URL configured."""
    if not webhook_url:
        return False
    poster(webhook_url, {"content": message})
    return True


def format_buy(item_name, price, qty, reason):
    return f"🟢 BUY {item_name} — {qty} @ {price:,} gp ({reason})"


def format_sell(item_name, price, reason):
    return f"🟡 SELL {item_name} @ {price:,} gp ({reason})"
```

- [ ] **Step 4: Run, verify pass**

Run: `python -m pytest tests/test_notify.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add bot/notify.py tests/test_notify.py
git commit -m "feat: add optional webhook notifier"
```

---

### Task 2: Bond goal refresh

**Files:**
- Modify: `bot/api_client.py`
- Create: `bot/goal.py`
- Test: `tests/test_goal.py`

Add `WikiClient.latest_item(item_id)` (single-item latest). `refresh_bond_goal(conn, client, now_iso)` writes `bond_price` (item 13190 high), defaults `bond_days` to 14 if unset, and sets `goal_period_start` if unset.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_goal.py
from bot import db, goal


class StubClient:
    def latest_item(self, item_id):
        assert item_id == 13190
        return {"high": 14000000, "low": 13300000}


def fresh():
    conn = db.connect(":memory:")
    db.init_db(conn)
    return conn


def test_refresh_sets_bond_price_and_defaults():
    conn = fresh()
    goal.refresh_bond_goal(conn, StubClient(), now_iso="2026-06-17T00:00:00+00:00")
    assert db.get_config(conn, "bond_price") == "14000000"
    assert db.get_config(conn, "bond_days") == "14"
    assert db.get_config(conn, "goal_period_start") == "2026-06-17T00:00:00+00:00"


def test_refresh_keeps_existing_period_start():
    conn = fresh()
    db.set_config(conn, "goal_period_start", "2026-06-01T00:00:00+00:00")
    goal.refresh_bond_goal(conn, StubClient(), now_iso="2026-06-17T00:00:00+00:00")
    assert db.get_config(conn, "goal_period_start") == "2026-06-01T00:00:00+00:00"
```

- [ ] **Step 2: Run, verify failure**

Run: `python -m pytest tests/test_goal.py -v`
Expected: FAIL — no module `bot.goal`.

- [ ] **Step 3: Add latest_item to api_client.py**

Add this method to `WikiClient` (after `latest`):

```python
    def latest_item(self, item_id):
        return self._get(f"/latest?id={item_id}")["data"][str(item_id)]
```

- [ ] **Step 4: Implement goal.py**

```python
# bot/goal.py
"""Keep the bond-price goal config fresh. Bond is item 13190."""

from datetime import datetime, timezone

from bot import db

BOND_ID = 13190


def refresh_bond_goal(conn, client, now_iso=None):
    now_iso = now_iso or datetime.now(timezone.utc).isoformat()
    bond = client.latest_item(BOND_ID)
    db.set_config(conn, "bond_price", str(bond["high"]))
    if db.get_config(conn, "bond_days") is None:
        db.set_config(conn, "bond_days", "14")
    if db.get_config(conn, "goal_period_start") is None:
        db.set_config(conn, "goal_period_start", now_iso)
```

- [ ] **Step 5: Run, verify pass**

Run: `python -m pytest tests/test_goal.py tests/test_api_client.py -v`
Expected: PASS (goal 2 + api_client unchanged).

- [ ] **Step 6: Commit**

```bash
git add bot/api_client.py bot/goal.py tests/test_goal.py
git commit -m "feat: add bond goal refresh and single-item latest"
```

---

### Task 3: Wire notifications + goal into the scheduler

**Files:**
- Modify: `bot/scheduler.py`
- Modify: `bot/main.py`
- Test: `tests/test_scheduler.py`

The scheduler gains an injectable `notifier` (default `notify.notify`) and a `goal_interval_s` throttle. After `evaluate`, it notifies for newly-created proposals and newly-created sell signals when a `notify_webhook` config is set. It refreshes the bond goal at most every `goal_interval_s`.

- [ ] **Step 1: Add a failing test**

Append to `tests/test_scheduler.py`:

```python
def test_tick_notifies_new_proposals():
    conn = db.connect(":memory:")
    db.init_db(conn)
    db.set_config(conn, "notify_webhook", "http://hook")
    runs.start_run(conn, "alwaysbuy", budget_gp=10_000)
    sent = []
    sched = PollScheduler(conn, StubClient(), watchlist=[1], loader=loader_stub,
                          notifier=lambda url, msg: sent.append(msg),
                          goal_interval_s=0)
    sched.tick(now=0.0)
    assert any("Item1" in m for m in sent)   # a buy notification fired


def test_tick_no_notify_without_webhook():
    conn = db.connect(":memory:")
    db.init_db(conn)
    runs.start_run(conn, "alwaysbuy", budget_gp=10_000)
    sent = []
    sched = PollScheduler(conn, StubClient(), watchlist=[1], loader=loader_stub,
                          notifier=lambda url, msg: sent.append(msg))
    sched.tick(now=0.0)
    assert sent == []
```

Note: `StubClient` in this test file needs a `latest_item` method for the goal refresh; add it to the existing `StubClient`:

```python
    def latest_item(self, item_id):
        return {"high": 14000000, "low": 13300000}
```

- [ ] **Step 2: Run, verify failure**

Run: `python -m pytest tests/test_scheduler.py -v`
Expected: FAIL — `PollScheduler` has no `notifier`/`goal_interval_s` kwargs.

- [ ] **Step 3: Update scheduler.py**

Update `PollScheduler.__init__` to add params and goal-timer state, and rewrite `tick`:

```python
    def __init__(self, conn, client, watchlist, interval_s=300,
                 timestep="24h", loader=load_strategies,
                 notifier=None, goal_interval_s=86400):
        self.conn = conn
        self.client = client
        self.watchlist = watchlist
        self.interval_s = interval_s
        self.timestep = timestep
        self.loader = loader
        from bot import notify as _notify
        self.notifier = notifier or _notify.notify
        self.goal_interval_s = goal_interval_s
        self._last_goal = None
        self._mapping = None
        self._history = None
        self._stop = threading.Event()
        self._thread = None
```

Replace `tick` with:

```python
    def tick(self, now=None):
        import time as _time
        from bot import db, positions as pos, goal as goal_mod, notify as notify_mod
        from bot.market import build_market_data
        now = _time.monotonic() if now is None else now
        self._ensure_context()

        # bond goal refresh (throttled)
        if self._last_goal is None or (now - self._last_goal) >= self.goal_interval_s:
            try:
                goal_mod.refresh_bond_goal(self.conn, self.client)
            except Exception:
                pass
            self._last_goal = now

        poll_once(self.client, self.conn)
        markets = build_market_data(self.conn, self._mapping, self._history,
                                    self.watchlist, now=now)
        market_map = {m.item_id: m for m in markets}

        webhook = db.get_config(self.conn, "notify_webhook")
        before_props = {p["id"] for p in pos.list_positions(self.conn, "proposed")}
        before_sells = {r["id"] for r in self.conn.execute(
            "SELECT id FROM signals WHERE type='sell'").fetchall()}

        evaluate(self.conn, market_map, now=now, loader=self.loader)

        if webhook:
            for p in pos.list_positions(self.conn, "proposed"):
                if p["id"] not in before_props:
                    self.notifier(webhook, notify_mod.format_buy(
                        p["item_name"], p["buy_price"], p["qty"], "signal"))
            for r in self.conn.execute(
                    "SELECT * FROM signals WHERE type='sell'").fetchall():
                if r["id"] not in before_sells:
                    self.notifier(webhook, notify_mod.format_sell(
                        r["item_id"], r["price"], r["reason"] or ""))
```

(Keep `_ensure_context`, `_loop`, `start`, `stop` unchanged.)

- [ ] **Step 4: Update main.py to enable goal refresh**

In `bot/main.py`, no signature change is required (the scheduler defaults handle notify+goal). Confirm `build()` still constructs `PollScheduler(sched_conn, client, watchlist=WATCHLIST)` — the defaults now also refresh the goal daily and notify if `notify_webhook` is configured. No code change needed beyond what exists; if a comment helps, add above the scheduler line:

```python
    # scheduler also refreshes the bond goal daily and sends webhook
    # notifications when config key 'notify_webhook' is set.
```

- [ ] **Step 5: Run scheduler tests + full suite**

Run: `python -m pytest tests/test_scheduler.py -v`
Expected: PASS (existing + 2 new).
Run: `python -m pytest`
Expected: PASS — all phases green.

- [ ] **Step 6: Commit**

```bash
git add bot/scheduler.py bot/main.py tests/test_scheduler.py
git commit -m "feat: scheduler sends notifications and refreshes bond goal"
```

---

### Task 4: One-click launcher + docs

**Files:**
- Create: `start-bot.bat`
- Create: `README.md`

CMD-free start: a `.bat` that launches the server with `pythonw` (no console window) and opens the dashboard. See [[Launch]].

- [ ] **Step 1: Create start-bot.bat**

```bat
@echo off
REM One-click launcher for the OSRS Flip Bot. Starts the server hidden and
REM opens the dashboard. Set OSRS_BOT_UA to your own contact before sharing.
cd /d "%~dp0"
if "%OSRS_BOT_UA%"=="" set OSRS_BOT_UA=osrs-flip-bot/1.0 (set OSRS_BOT_UA)
start "" /b pythonw -m bot.main
timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:8000
```

- [ ] **Step 2: Create README.md**

```markdown
# OSRS Flip Bot

Local web dashboard that advises buy/sell decisions in the OSRS Grand
Exchange. **It never trades in-game** — it proposes, you click in the GE.

## Run
```
pip install -r requirements.txt
python -m bot.main          # then open http://127.0.0.1:8000
```
Or double-click `start-bot.bat` (Windows, no console window).

Set your contact in the `OSRS_BOT_UA` environment variable (the OSRS Wiki API
asks for it).

## Auto-start at login (optional)
Press `Win+R`, type `shell:startup`, and drop a shortcut to `start-bot.bat`
there. The bot then runs from login; just open the dashboard bookmark.

## Notifications (optional)
Set a Discord webhook URL:
```
curl -X POST http://127.0.0.1:8000/api/config/notify_webhook -H "Content-Type: application/json" -d "{\"value\":\"https://discord.com/api/webhooks/...\"}"
```

## Tests
```
python -m pytest
```

## How it works
See the Obsidian vault under `Bot vault/` (start at `Home.md`).
```

- [ ] **Step 3: Verify the suite still passes**

Run: `python -m pytest`
Expected: PASS — all phases green (no code change in this task).

- [ ] **Step 4: Commit**

```bash
git add start-bot.bat README.md
git commit -m "docs: add one-click launcher and README"
```

---

## Self-Review Notes

- **Spec coverage:** notifications ([[Launch]] notify) via injectable webhook (notify.py); bond goal kept live (goal.py + scheduler throttle); CMD-free launcher + auto-start docs (start-bot.bat + README). The scheduler now drives all three of poll → evaluate → notify → goal.
- **Type consistency:** `notify(webhook_url, message, poster)` and `PollScheduler(..., notifier=, goal_interval_s=)` match their tests. `refresh_bond_goal(conn, client, now_iso)` matches. `WikiClient.latest_item(item_id)` returns the single item dict used by goal.py.
- **Placeholder scan:** complete code in every step; the only non-automated artifact is the `.bat` (inherently manual), backed by the README.
- **Note:** sell notifications use `item_id` as the name (the signals row has no item_name). A future refinement can join the position for a friendly name; acceptable for now.

## Done
After Phase 6 the bot is feature-complete per the [[OSRS Flip Bot Design Spec|spec]]. Remaining is operational: move to an always-on Oracle Cloud Free VM ([[Launch]]) when desired.
