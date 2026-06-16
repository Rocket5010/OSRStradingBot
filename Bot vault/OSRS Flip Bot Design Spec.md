# OSRS Flip Bot — Design Spec

> Index: [[Home]] · See also [[Architecture Overview]] · [[Strategy System]] · [[Build Phases]]

**Date:** 2026-06-16
**Status:** Approved design, pending implementation plan

## Summary

A local web dashboard (dark + gold theme) powered by a single Python process.
It polls the OSRS Wiki Real-time Prices API every 5 minutes, runs pluggable
strategies (active flipping + investment strategies), and proposes
capital-aware buy/sell signals. The user accepts signals in the dashboard
(bot = brain, user = hand), which logs positions. The bot tracks positions
with stop-loss and max-hold-time, measures progress toward a "one bond every
14 days" goal, and includes backtesting to find the best strategy. Launches
without touching the command line. It never auto-trades inside the game.

## Hard Constraints

- **No in-game automation.** There is no public API to buy/sell in the Grand
  Exchange, and auto-clicking the game client is botting → account ban. The bot
  is an advisor only. The user performs the physical GE clicks.
- **Free only.** No paid services. The OSRS Wiki API is free with no monthly
  quota (asks for a `User-Agent` and ~1 req/sec politeness). Compute must stay
  within an always-on free tier (target: Oracle Cloud Free VM later; local PC
  now).
- **Poll cadence = 5 min.** The `/5m` aggregate is recomputed every 5 minutes;
  polling faster yields identical data. Cadence is configurable but never
  faster than data granularity.

## Requirements

- Two modes: active flipping + investing.
- Web dashboard, runs locally, notification channel TBD (Discord/Telegram).
- Bot decides everything; user accepts in dashboard → position logged → user
  places the GE order. User never analyzes manually.
- Position lifecycle with cancel/withdraw for orders that don't fill in-game.
- Strategies are started manually by the user; nothing runs by default. The
  user sets a gp budget per strategy at start. A strategy proposes buys only
  within its own budget. Multiple strategies can run at once. Currently only an
  investing strategy is started; flipping is started when actively playing.
- Sell logic (hybrid): target margin + stop-loss + max hold time.
- Goal: ~1M gp/day net → one bond (~14M) every 14 days, with a progress
  tracker. Bond price fetched live (item id 13190).
- Host-agnostic: local now, Oracle-VM-ready later, no rewrite.
- Pretty UI, decoupled from backend so styling can change freely.
- Pluggable strategies: drop a `.py` file in `strategies/`, select it in the
  dashboard. No code changes elsewhere.

## Architecture

Single Python process (`app.py`):

```
Poller (async, every 5m) ──▶ OSRS Wiki API
        │ raw prices + volume
        ▼
Strategy (pure functions) ◀──▶ SQLite (state) ◀──▶ Position manager
        │ signals
        ▼
FastAPI (JSON API) ──▶ Notifier (Discord/Telegram)
        │ HTTP/JSON
        ▼
Dashboard (HTML/CSS/JS, presentation only — talks to JSON API)
```

Frontend and backend communicate **only** via a JSON API. The dashboard is
pure presentation; restyling touches only `static/`, never backend logic.
Theme is driven by CSS variables (`--gold`, `--bg`, etc.).

### Modules (one responsibility each, testable in isolation)

| Module | Responsibility | Depends on |
|---|---|---|
| `api_client.py` | Fetch from Wiki API, cache, rate-limit | — |
| `poller.py` | Run every 5 min, feed strategy | api_client |
| `strategies/base.py` | `Strategy` interface + signal datatypes | — |
| `strategy_loader.py` | Auto-discover + load strategies from folder | base |
| `strategy/*` | Individual strategies (pure, no I/O) | base |
| `positions.py` | Position lifecycle + P/L | db |
| `db.py` | SQLite: positions, capital, signal history, cache | — |
| `notify.py` | Send notifications (pluggable: Discord/Telegram) | — |
| `web.py` | FastAPI: JSON API + serve dashboard | all above |
| `static/` | dashboard.html/css/js — presentation only | JSON API only |

## Strategy Plugin Contract

```python
class Strategy:
    name: str            # shown in dashboard dropdown
    description: str
    def find_buys(self, market, capital) -> list[BuySignal]: ...
    def should_sell(self, position, market) -> SellDecision: ...
    def default_params(self) -> dict: ...   # tunable in dashboard
```

At startup the loader auto-discovers every file in `strategies/` and populates
the dashboard dropdown. Tunable params are exposed as dashboard fields per
strategy. The backend calls only the contract — it does not know which strategy
runs.

**Manual start + per-strategy budget:** nothing runs by default. The user starts
a strategy and sets its gp budget at start; the strategy proposes buys only
within that budget. Multiple strategies can run at once, each with its own
allocation. Running strategies + budgets are stored in `strategy_runs`.

The same contract enables backtesting: run a strategy against historical
`/timeseries` data.

### Strategy roster

Active flipping:
- `margin_flip` — `margin = high − tax − low > min_margin` AND `vol_1h >
  min_vol` AND `roi > min_roi`. Sized against free capital + buy limit. Sell at
  target margin; stop-loss at −X%; short max hold (hours).

Investing — mean-reversion family (good in sideways markets):
- `mean_reversion` — buy when `price < mean − k·σ`; sell back to mean.
- `bollinger` — buy at lower band; sell at middle/upper band.
- `rsi` — buy RSI < 30 (oversold); sell RSI > 70 (overbought).
- `crash_recovery` — buy after a >X% drop with a stable historical floor
  (overreaction to update/nerf); sell back toward floor.

Investing — trend/momentum family (good in trending markets):
- `ma_crossover` — buy on golden cross (fast MA over slow MA); sell on death
  cross.
- `momentum` — buy when price + volume rise N days running; sell when trend
  flattens/reverses.
- `breakout` — buy on break above N-day high + volume spike; sell on trailing
  stop.

All investment strategies share `stop_loss` and `max_hold` params plus their
own. Backtest finds which fits OSRS best; the two families win in different
market conditions, so the winner can vary per item category.

## Data Model (SQLite)

```
positions
  id, item_id, item_name, strategy,
  state            -- proposed|accepted|filled|selling|sold|cancelled|dismissed
  buy_price, qty, buy_tax,
  sell_target, stop_loss, max_hold_until,
  sell_price, realized_pl,
  created_at, filled_at, closed_at

signals            -- log of every proposal (history/analysis)
  id, item_id, strategy, type(buy|sell),
  price, margin, roi, reason, created_at, status(shown|accepted|dismissed)

strategy_runs      -- a started strategy with its own gp budget
  id, strategy, params_json,
  budget_gp,         -- user-set at start
  spent_gp,          -- committed to open positions
  state(running|stopped), started_at, stopped_at

config             -- key/value: total capital, poll cadence,
                   -- bond-goal settings, notification webhook

price_cache        -- last API snapshot (survives restart)
  item_id, low, high, vol_1h, ts
```

### Position lifecycle

```
proposed ──accept──▶ accepted ──fill──▶ filled ──sell-signal──▶ selling ──fill──▶ sold
   │                    │                                          │
   └──dismiss──▶ dismissed └──withdraw──▶ cancelled    cancel──────┘
```

User drives state via dashboard buttons. The bot proposes `filled`/`selling`
transitions; the user confirms when the GE order actually fills.

### GE tax / P/L

```
ge_tax(price)  = min(floor(price * 0.02), 5_000_000)   # per item
realized_pl    = (sell_price - ge_tax(sell_price)) * qty - buy_price * qty
```

## Backtesting

Runs the strategy contract against `/timeseries` (5m/1h/6h/24h steps, ~365
points per call; use 24h step for up to ~1 year). Report: profit, hit rate, max
drawdown per strategy. Conservative fill assumptions (partial fills, buy
limits, tax) so results don't lie. Backtest is guidance, not gospel — GE data
has no order-book depth, so fills are assumed.

## Build Phases

Build the whole thing to completion — no early MVP. Phases are a dependency
order, not a stopping point.

- **Phase 1 — Core engine:** `api_client` (incl. `/timeseries`), `db` (full
  schema), `strategies/base`, `strategy_loader`, `poller`.
- **Phase 2 — Strategies:** all of them — `margin_flip` + investing
  (`mean_reversion`, `bollinger`, `rsi`, `crash_recovery`, `ma_crossover`,
  `momentum`, `breakout`).
- **Phase 3 — Backtest engine:** run the contract over `/timeseries`, rank
  strategies (profit, hit rate, drawdown).
- **Phase 4 — Web backend:** `web.py` JSON API; `positions.py` + state machine;
  manual start + per-strategy budget (`strategy_runs`).
- **Phase 5 — Dashboard:** `static/` from the mockup; strategy start/stop +
  budget input; accept/sell/cancel wired to API; live refresh; bond tracker;
  backtest view.
- **Phase 6 — Polish:** one-click `.bat` launcher + auto-start at login;
  `notify.py`.
- **Later (not now):** move to Oracle Cloud Free VM.

## Launch (CMD-free)

1. One-click `.bat`/shortcut: starts the process hidden, opens the dashboard in
   the browser.
2. Optional auto-start at Windows login (Task Scheduler / startup folder).
3. Later on Oracle VM: always on; user just opens a URL.

## Stack

Python 3.13 · FastAPI · SQLite · vanilla HTML/CSS/JS · Chart.js · `httpx`/stdlib
for API calls. Minimal dependencies (`fastapi`, `uvicorn`, `httpx`).

## API Reference (OSRS Wiki)

Base: `https://prices.runescape.wiki/api/v1/osrs`
- `/latest` — live high/low per item
- `/5m`, `/1h` — time-averaged price + volume
- `/timeseries?timestep=24h&id=ID` — historical candles
- `/mapping` — item meta (buy limit, members flag, value)
- Requires `User-Agent` header with contact info.

## Conventions

- Code and GUI in English by default (unless specified otherwise).
- Chat in Norwegian.
