# Auto-pilot

The bot picks the strategy itself — no manual strategy-starting. Part of [[Home]].

## How it works
- **Diversified**: the auto-budget (config `auto_budget`) is split equally across
  the **top-N** positively-scored strategies (N = config `auto_strategies`,
  default 3). Each gets its own running **auto-run** (`strategy_runs.auto = 1`)
  with `budget = auto_budget / N`. Spreading capital lowers the damage when the
  single best strategy stops working — better odds, lower variance.
- Weekly the [[scheduler]] runs a tuned backtest over the [[Watchlist Curator|
  watchlist]] (or a default basket) and saves the [[Backtesting|ranking]] (with
  walk-forward-tuned params per strategy).
- Every tick the scheduler reconciles the auto-runs to the current top-N via
  `runs.ensure_auto_runs`: updates budgets/params in place, creates new ones, and
  **stops** strategies that dropped out. A stopped run keeps **selling** its open
  positions (the sell loop is run-state-independent).
- New buys use each auto-run's strategy + tuned params. **Each position stores the
  strategy + params that bought it** (`positions.params_json`), so old positions
  still **sell the way they were bought** after a re-pick.
- Set `auto_budget` to 0 to pause (stops all auto-runs; open positions still sell).

## Why this design
- Switching strategies must not break in-flight positions → per-position
  strategy+params (see [[Position Lifecycle]]).
- One auto-run per strategy keeps per-strategy budget accounting clean and lets
  the engine's buy loop (which iterates all running runs) trade them in parallel.
- Diversifying across the top-N trades some peak return for reliability — aligned
  with the "smaller margin, higher chance" goal.

## User decisions baked in
- Re-pick cadence: **weekly**.
- On switch: **keep** old positions, sell via their own strategy (no force-sell).
- **Auto-only** — the manual start form was removed from the dashboard.

## Setup
1. Settings → set **Capital** + **Auto-budget** → Save.
2. **Run backtest** once to seed the ranking (then weekly auto-refresh).
3. Auto-pilot starts within a tick or two; the **Auto-pilot** panel shows the
   active strategy/budget/spent.
