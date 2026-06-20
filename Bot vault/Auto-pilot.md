# Auto-pilot

The bot picks the strategy itself — no manual strategy-starting. Part of [[Home]].

## How it works
- A single **auto-run** (`strategy_runs.auto = 1`, one row) holds the user's
  **auto-budget** (config `auto_budget`) as a single capital pool.
- Weekly the [[scheduler]] runs a real backtest over the [[Watchlist Curator|
  watchlist]] (or a default basket) and saves the [[Backtesting|ranking]].
- Every tick the scheduler points the auto-run at the **current best** strategy
  (top of the ranking, only if its profit > 0) via `runs.ensure_auto_run`.
- New buys use the auto-run's current strategy. **Each position stores the
  strategy + params that bought it** (`positions.params_json`), so when the
  strategy later changes, old positions still **sell the way they were bought**.
- Budget is one pool: `available = auto_budget − spent_gp`. Set `auto_budget` to
  0 to pause.

## Why this design
- Switching strategies must not break in-flight positions → per-position
  strategy+params (see [[Position Lifecycle]]).
- One mutable auto-run keeps budget accounting simple (single pool) while still
  letting the active strategy change weekly.

## User decisions baked in
- Re-pick cadence: **weekly**.
- On switch: **keep** old positions, sell via their own strategy (no force-sell).
- **Auto-only** — the manual start form was removed from the dashboard.

## Setup
1. Settings → set **Capital** + **Auto-budget** → Save.
2. **Run backtest** once to seed the ranking (then weekly auto-refresh).
3. Auto-pilot starts within a tick or two; the **Auto-pilot** panel shows the
   active strategy/budget/spent.
