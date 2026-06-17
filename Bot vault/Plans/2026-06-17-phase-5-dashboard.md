# Phase 5 — Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

> Index: [[Home]] · Spec: [[OSRS Flip Bot Design Spec]] · Phases: [[Build Phases]] · Prev: [[2026-06-17-phase-4b-live-engine]]

**Goal:** Ship the dark+gold web dashboard from the approved mockup, wired to the Phase 4 JSON API — strategy start/stop with budget, live signal/position tables with accept/sell/cancel actions, capital + bond-goal tracker — served by the existing FastAPI app.

**Architecture:** A small `/api/overview` endpoint aggregates the numbers the dashboard header needs (capital, free/committed, profit today, bond price + goal progress, open-position counts) so the frontend makes one cheap call. Static files (`bot/static/index.html`, `app.js`, `style.css`) are served by the FastAPI app via `StaticFiles`. The frontend is vanilla HTML/CSS/JS (no build step): it polls the JSON API every few seconds and re-renders. Theme lives entirely in CSS variables so restyling never touches Python — the [[Architecture Overview|frontend ⟂ backend]] rule.

**Tech Stack:** Python 3.13, `fastapi` `StaticFiles`, vanilla HTML/CSS/JS, `pytest` (+ FastAPI `TestClient` for the API additions). Frontend logic is verified manually in a browser; the API additions are unit-tested.

---

## File Structure

```
bot/
├── web.py             # + /api/overview, + mount StaticFiles at /
└── static/
    ├── index.html     # dashboard markup (dark+gold)
    ├── style.css      # theme via CSS variables
    └── app.js         # fetch API, render tables, wire buttons
tests/
└── test_web.py        # + overview endpoint tests
```

---

### Task 1: Overview endpoint

**Files:**
- Modify: `bot/web.py`
- Modify: `tests/test_web.py`

Aggregate header numbers in one call. Capital + bond settings come from `config` (keys: `capital`, `bond_price`, `bond_days`, `goal_period_start`). "Profit today" is summed from positions sold today; "committed" is the sum of open (accepted/filled/selling) position cost; "free" is capital − committed.

- [ ] **Step 1: Add failing tests**

Append to `tests/test_web.py`:

```python
def test_overview_defaults_zero():
    c = client()
    o = c.get("/api/overview").json()
    assert o["capital"] == 0
    assert o["committed"] == 0
    assert o["free"] == 0
    assert o["open_positions"] == 0
    assert "bond_price" in o and "period_profit" in o


def test_overview_reflects_capital_and_committed():
    c = client()
    c.post("/api/config/capital", json={"value": "1000000"})
    rid = c.post("/api/runs", json={"strategy": "rsi", "budget_gp": 1000000}).json()["id"]
    pid = c.post("/api/positions", json={
        "strategy": "rsi", "item_id": 2, "item_name": "Cb",
        "buy_price": 100, "qty": 100, "run_id": rid}).json()["id"]
    c.post(f"/api/positions/{pid}/accept")   # commits 100*100 = 10_000
    o = c.get("/api/overview").json()
    assert o["capital"] == 1000000
    assert o["committed"] == 10000
    assert o["free"] == 990000
    assert o["open_positions"] == 1
```

- [ ] **Step 2: Run, verify failure**

Run: `python -m pytest tests/test_web.py -k overview -v`
Expected: FAIL — `/api/overview` 404.

- [ ] **Step 3: Add the endpoint to web.py**

Add near the top of the module (after the imports):

```python
from datetime import datetime, timezone

_OPEN = ("accepted", "filled", "selling")
```

Add this route inside `create_app`, before `return app`:

```python
    @app.get("/api/overview")
    def overview():
        def cfg_int(key, default=0):
            v = db_mod.get_config(conn, key)
            return int(v) if v is not None else default

        capital = cfg_int("capital")
        committed_row = conn.execute(
            "SELECT COALESCE(SUM(buy_price * qty), 0) AS s FROM positions "
            f"WHERE state IN ({','.join('?' * len(_OPEN))})", _OPEN).fetchone()
        committed = committed_row["s"]
        open_count = conn.execute(
            f"SELECT COUNT(*) AS c FROM positions WHERE state IN "
            f"({','.join('?' * len(_OPEN))})", _OPEN).fetchone()["c"]
        period_start = db_mod.get_config(conn, "goal_period_start") or ""
        profit_row = conn.execute(
            "SELECT COALESCE(SUM(realized_pl), 0) AS s FROM positions "
            "WHERE state='sold' AND closed_at >= ?", (period_start,)).fetchone()
        bond_price = cfg_int("bond_price", 0)
        return {
            "capital": capital,
            "committed": committed,
            "free": capital - committed,
            "open_positions": open_count,
            "period_profit": profit_row["s"],
            "bond_price": bond_price,
            "bond_days": cfg_int("bond_days", 14),
            "goal_progress": (profit_row["s"] / bond_price) if bond_price else 0.0,
        }
```

- [ ] **Step 4: Run, verify pass**

Run: `python -m pytest tests/test_web.py -k overview -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add bot/web.py tests/test_web.py
git commit -m "feat: add /api/overview aggregate endpoint"
```

---

### Task 2: Serve static files

**Files:**
- Create: `bot/static/index.html` (placeholder for now)
- Modify: `bot/web.py`
- Modify: `tests/test_web.py`

Mount the static directory at `/` so the dashboard is served by the same app. API routes keep their `/api/...` prefix and are unaffected.

- [ ] **Step 1: Create a minimal index.html placeholder**

```html
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Flip Bot</title></head>
<body><div id="app">loading</div></body></html>
```

- [ ] **Step 2: Add a failing test**

Append to `tests/test_web.py`:

```python
def test_root_serves_dashboard():
    c = client()
    r = c.get("/")
    assert r.status_code == 200
    assert "<div id=\"app\">" in r.text


def test_api_still_works_after_mount():
    c = client()
    assert c.get("/api/strategies").status_code == 200
```

- [ ] **Step 3: Run, verify failure**

Run: `python -m pytest tests/test_web.py -k "dashboard or after_mount" -v`
Expected: FAIL — `/` returns 404.

- [ ] **Step 4: Mount StaticFiles in web.py**

Add import at top:

```python
from fastapi.staticfiles import StaticFiles
```

At the END of `create_app`, immediately before `return app`, mount the static dir (must be after all `/api` routes are registered):

```python
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
```

- [ ] **Step 5: Run, verify pass**

Run: `python -m pytest tests/test_web.py -k "dashboard or after_mount" -v`
Expected: PASS (2 passed). Then run the full `tests/test_web.py` to confirm no API route regressed.

- [ ] **Step 6: Commit**

```bash
git add bot/static/index.html bot/web.py tests/test_web.py
git commit -m "feat: serve static dashboard from FastAPI"
```

---

### Task 3: Dashboard markup + theme

**Files:**
- Modify: `bot/static/index.html`
- Create: `bot/static/style.css`

Build the dark+gold layout from the approved mockup: header (brand + live status), four stat cards, a bond-goal bar, and two panels (signals/buy table, positions table). No data yet — `app.js` (Task 4) fills it. IDs/classes are the contract `app.js` depends on.

- [ ] **Step 1: Write index.html**

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OSRS Flip Bot</title>
<link rel="stylesheet" href="/style.css">
</head>
<body>
<div class="wrap">
  <header class="topbar">
    <div class="brand"><div class="logo">GE</div>
      <div><h1>Flip Bot <small>· OSRS</small></h1></div></div>
    <div class="status"><span class="dot"></span> <span id="status-text">connecting…</span></div>
  </header>

  <section class="stats">
    <div class="card"><div class="label">Capital</div>
      <div class="big" id="stat-capital">–</div>
      <div class="sub" id="stat-capital-sub"></div></div>
    <div class="card"><div class="label">Profit this period</div>
      <div class="big" id="stat-profit">–</div>
      <div class="sub">toward bond goal</div></div>
    <div class="card"><div class="label">Open positions</div>
      <div class="big" id="stat-open">–</div>
      <div class="sub" id="stat-open-sub"></div></div>
    <div class="card"><div class="label">Bond price</div>
      <div class="big" id="stat-bond">–</div>
      <div class="sub">live target</div></div>
  </section>

  <section class="goal">
    <div class="goal-head"><h3>🎯 Bond goal · this period</h3>
      <span id="goal-text"></span></div>
    <div class="bar"><span id="goal-bar"></span></div>
  </section>

  <section class="runs card">
    <h2>Strategies</h2>
    <div class="run-form">
      <select id="run-strategy"></select>
      <input id="run-budget" type="number" placeholder="budget (gp)">
      <button id="run-start" class="btn accept">Start</button>
    </div>
    <table><thead><tr><th>Strategy</th><th>Budget</th><th>Spent</th>
      <th>State</th><th></th></tr></thead>
      <tbody id="runs-body"></tbody></table>
  </section>

  <div class="panels">
    <section class="panel">
      <h2>Buy signals</h2>
      <table><thead><tr><th>Item</th><th>Buy</th><th>Qty</th><th></th></tr></thead>
        <tbody id="buys-body"></tbody></table>
    </section>
    <section class="panel">
      <h2>Your positions</h2>
      <table><thead><tr><th>Item</th><th>State</th><th>P/L</th><th></th></tr></thead>
        <tbody id="positions-body"></tbody></table>
    </section>
  </div>

  <p class="legend" id="legend">Bot proposes — you place trades in the GE.</p>
</div>
<script src="/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Write style.css**

```css
:root{
  --bg:#0f1115; --panel:#171a21; --panel2:#1e222b; --border:#2a2f3a;
  --text:#e6e8ec; --muted:#8a92a3; --gold:#f4c542; --green:#3fb950;
  --red:#f85149; --blue:#58a6ff;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif;padding:24px;line-height:1.4}
.wrap{max-width:1100px;margin:0 auto}
.topbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:24px}
.brand{display:flex;align-items:center;gap:12px}
.brand .logo{width:38px;height:38px;border-radius:9px;background:linear-gradient(135deg,var(--gold),#b8860b);display:flex;align-items:center;justify-content:center;font-weight:800;color:#1a1a1a}
.brand h1{font-size:18px} .brand small{color:var(--muted);font-weight:400}
.status{display:flex;align-items:center;gap:8px;font-size:13px;color:var(--muted)}
.dot{width:9px;height:9px;border-radius:50%;background:var(--green);box-shadow:0 0 8px var(--green)}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:20px}
.card{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:16px}
.card .label{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px}
.card .big{font-size:24px;font-weight:700;margin-top:6px}
.card .sub{font-size:12px;color:var(--muted);margin-top:4px}
.up{color:var(--green)} .down{color:var(--red)}
.goal{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:16px;margin-bottom:20px}
.goal-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}
.goal-head h3{font-size:14px} #goal-text{color:var(--gold);font-weight:700}
.bar{height:12px;background:var(--panel2);border-radius:6px;overflow:hidden}
.bar>span{display:block;height:100%;width:0;background:linear-gradient(90deg,var(--gold),#ffe08a)}
.runs{margin-bottom:20px}
.run-form{display:flex;gap:10px;margin:12px 0}
.run-form select,.run-form input{background:var(--panel2);border:1px solid var(--border);color:var(--text);border-radius:7px;padding:8px}
.panels{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.panel,.runs{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:16px}
h2{font-size:14px;margin-bottom:8px}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;color:var(--muted);font-weight:500;font-size:11px;text-transform:uppercase;padding:8px 4px}
td{padding:10px 4px;border-top:1px solid var(--border)}
.btn{border:none;border-radius:7px;padding:6px 12px;font-size:12px;font-weight:600;cursor:pointer}
.btn.accept{background:var(--green);color:#04210c}
.btn.sell{background:var(--gold);color:#241c00}
.btn.ghost{background:transparent;border:1px solid var(--border);color:var(--muted)}
.tagsell{color:var(--gold);font-weight:700}
.mut{color:var(--muted)}
.legend{font-size:11px;color:var(--muted);margin-top:18px;text-align:center}
@media(max-width:760px){.stats{grid-template-columns:repeat(2,1fr)}.panels{grid-template-columns:1fr}}
```

- [ ] **Step 3: Verify it serves**

Run: `python -m pytest tests/test_web.py -k dashboard -v`
Expected: PASS — `test_root_serves_dashboard` still green (markup now includes `<div id="app">`? No — update that test is not needed; the test only checks status 200 and the placeholder string was removed). Adjust: confirm the test still asserts something present. If `test_root_serves_dashboard` asserted `<div id="app">`, update it in this step to assert `id="status-text"` instead:

```python
def test_root_serves_dashboard():
    c = client()
    r = c.get("/")
    assert r.status_code == 200
    assert "status-text" in r.text
```

- [ ] **Step 4: Commit**

```bash
git add bot/static/index.html bot/static/style.css tests/test_web.py
git commit -m "feat: dashboard markup and dark+gold theme"
```

---

### Task 4: Frontend logic (app.js)

**Files:**
- Create: `bot/static/app.js`

Vanilla JS: load strategies into the dropdown, render runs/positions, wire Start/Stop/Accept/Sell/Cancel/Dismiss, poll `/api/overview` + `/api/positions` + `/api/runs` every 5s. No framework, no build.

- [ ] **Step 1: Write app.js**

```javascript
const $ = (id) => document.getElementById(id);
const fmt = (n) => {
  n = Number(n) || 0;
  if (Math.abs(n) >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (Math.abs(n) >= 1e3) return (n / 1e3).toFixed(0) + "K";
  return String(n);
};
async function api(path, method = "GET", body) {
  const opt = { method, headers: { "Content-Type": "application/json" } };
  if (body) opt.body = JSON.stringify(body);
  const r = await fetch("/api" + path, opt);
  if (!r.ok) throw new Error(path + " " + r.status);
  return r.status === 204 ? null : r.json();
}

async function loadStrategies() {
  const list = await api("/strategies");
  $("run-strategy").innerHTML = list
    .map((s) => `<option value="${s.name}">${s.name}</option>`).join("");
}

async function startRun() {
  const strategy = $("run-strategy").value;
  const budget_gp = parseInt($("run-budget").value || "0", 10);
  if (!budget_gp) return;
  await api("/runs", "POST", { strategy, budget_gp });
  $("run-budget").value = "";
  refresh();
}

function renderRuns(runs) {
  $("runs-body").innerHTML = runs.map((r) => `
    <tr><td>${r.strategy}</td><td>${fmt(r.budget_gp)}</td>
    <td>${fmt(r.spent_gp)}</td><td>${r.state}</td>
    <td>${r.state === "running"
      ? `<button class="btn ghost" onclick="stopRun(${r.id})">Stop</button>` : ""}</td></tr>`
  ).join("");
}
async function stopRun(id) { await api(`/runs/${id}/stop`, "POST"); refresh(); }

function renderPositions(positions) {
  const buys = positions.filter((p) => p.state === "proposed");
  $("buys-body").innerHTML = buys.length ? buys.map((p) => `
    <tr><td>${p.item_name}</td><td>${fmt(p.buy_price)}</td><td>${p.qty}</td>
    <td><button class="btn accept" onclick="act(${p.id},'accept')">Accept</button>
    <button class="btn ghost" onclick="act(${p.id},'dismiss')">Dismiss</button></td></tr>`
  ).join("") : `<tr><td colspan="4" class="mut">No buy signals</td></tr>`;

  const held = positions.filter((p) =>
    ["accepted", "filled", "selling"].includes(p.state));
  $("positions-body").innerHTML = held.length ? held.map((p) => {
    const pl = p.realized_pl != null ? fmt(p.realized_pl) : "–";
    let action = "";
    if (p.state === "accepted") action =
      `<button class="btn accept" onclick="act(${p.id},'fill')">Filled</button>
       <button class="btn ghost" onclick="act(${p.id},'cancel')">Cancel</button>`;
    else if (p.state === "filled") action =
      `<button class="btn sell" onclick="act(${p.id},'sell')">Sell</button>
       <button class="btn ghost" onclick="act(${p.id},'cancel')">Cancel</button>`;
    else if (p.state === "selling") action =
      `<button class="btn accept" onclick="sold(${p.id})">Sold</button>
       <button class="btn ghost" onclick="act(${p.id},'cancel')">Cancel</button>`;
    return `<tr><td>${p.item_name}</td><td class="mut">${p.state}</td>
      <td>${pl}</td><td>${action}</td></tr>`;
  }).join("") : `<tr><td colspan="4" class="mut">No open positions</td></tr>`;
}
async function act(id, action) { await api(`/positions/${id}/${action}`, "POST"); refresh(); }
async function sold(id) {
  const price = prompt("Sell price (gp)?");
  if (!price) return;
  await api(`/positions/${id}/sold`, "POST", { sell_price: parseInt(price, 10) });
  refresh();
}

function renderOverview(o) {
  $("stat-capital").textContent = fmt(o.capital);
  $("stat-capital-sub").textContent = `${fmt(o.free)} free · ${fmt(o.committed)} committed`;
  $("stat-profit").textContent = (o.period_profit >= 0 ? "+" : "") + fmt(o.period_profit);
  $("stat-profit").className = "big " + (o.period_profit >= 0 ? "up" : "down");
  $("stat-open").textContent = o.open_positions;
  $("stat-bond").textContent = fmt(o.bond_price);
  const pct = Math.max(0, Math.min(1, o.goal_progress)) * 100;
  $("goal-bar").style.width = pct + "%";
  $("goal-text").textContent = `${fmt(o.period_profit)} / ${fmt(o.bond_price)}`;
}

async function refresh() {
  try {
    const [overview, runs, positions] = await Promise.all([
      api("/overview"), api("/runs"), api("/positions"),
    ]);
    renderOverview(overview);
    renderRuns(runs);
    renderPositions(positions);
    $("status-text").textContent = "live · updated " + new Date().toLocaleTimeString();
  } catch (e) {
    $("status-text").textContent = "disconnected";
  }
}

$("run-start").addEventListener("click", startRun);
loadStrategies().then(refresh);
setInterval(refresh, 5000);
```

- [ ] **Step 2: Manual verification (no automated test for JS)**

Start the app: `python -m bot.main` then open `http://127.0.0.1:8000`. Confirm: strategies populate the dropdown; starting a run adds a row; the stat cards and goal bar render. (For an automated smoke check that the file is served, the test below suffices.)

- [ ] **Step 3: Add a serve test**

Append to `tests/test_web.py`:

```python
def test_appjs_served():
    c = client()
    r = c.get("/app.js")
    assert r.status_code == 200
    assert "refresh" in r.text
```

- [ ] **Step 4: Run, verify pass**

Run: `python -m pytest tests/test_web.py -k appjs -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest`
Expected: PASS — all phases green.

- [ ] **Step 6: Commit**

```bash
git add bot/static/app.js tests/test_web.py
git commit -m "feat: dashboard frontend logic"
```

---

## Self-Review Notes

- **Spec coverage:** dark+gold dashboard from the mockup (index.html + style.css), strategy start/stop + budget input (runs form), buy-signal table with accept/dismiss, positions table with fill/sell/sold/cancel, capital + free/committed + bond-goal tracker (/api/overview + header), live refresh (5s poll). Frontend talks only to the JSON API — backend untouched by styling. Theme via CSS variables ([[Conventions]]).
- **Type consistency:** `app.js` calls exactly the endpoints from Phase 4a (`/api/strategies`, `/api/runs`, `/api/runs/{id}/stop`, `/api/positions`, `/api/positions/{id}/{accept|fill|sell|sold|cancel|dismiss}`) plus the new `/api/overview`. The `sold` action posts `{sell_price}` matching `SellBody`. Element IDs in index.html match every `$()` lookup in app.js.
- **Placeholder scan:** complete code in every step. The only non-automated step is the browser check (Task 4 Step 2), which is inherent to UI work; a served-file test backs it up.
- **Note:** StaticFiles is mounted at `/` LAST so it never shadows `/api/*` routes. Bond price / goal-period config are set elsewhere (Phase 6 or manually via `/api/config/bond_price` etc.); the overview degrades gracefully to zeros.

## Next
Phase 6 — launcher (one-click `.bat` + auto-start) + notifications (`notify.py`) + a small job to refresh `bond_price` and `goal_period_start` config.
