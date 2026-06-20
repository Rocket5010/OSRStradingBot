# Watchlist Curator

Finds new opportunities automatically so the bot isn't stuck on a fixed item list. Part of [[Build Phases|Phase 7]]. Module: `bot/curator.py`.

## What it does
On a slow cadence (`curate_interval_s`, default 7 days), the [[Modules|scheduler]] runs:
1. **Screen (two buckets)** — `screen_two_bucket` merges two candidate sets from [[Data Model|price_cache]]:
   - **Liquid** — top N by `vol_1h` (cheap, fast-flipping items; the original behaviour).
   - **Value** — expensive items (`low >= value_min_price`, default 100k) at a much lower volume floor (default 10), ranked by `spread * vol_1h`. Without this bucket the volume-DESC sort buries every expensive high-margin item (whips, armour, 3rd-age) under cheap runes. No API cost — data is already polled.
2. **Backtest** — for each candidate, fetch [[OSRS Wiki API|/timeseries]] and run the configured investing strategy through the Phase 3 [[Backtesting|backtest engine]] (with `max_hold_steps`).
3. **Rank** — sort by **risk-adjusted gp/day** ([[Backtesting|risk_score]]), drop zero-trade / high-drawdown / unprofitable, keep the top N.
4. **Save** — write the winners to the `watchlist` [[Data Model|config]] key.

## How the live engine uses it
The scheduler reads the watchlist from config each tick (`curator.get_watchlist`, falling back to the hardcoded default until the first curation). [[Strategy System|Strategies]] then evaluate over the curated list. So the same [[Strategy System|Strategy contract]] that picks the strategy also picks the items.

## Why slow cadence
Backtesting hundreds of candidates means hundreds of `/timeseries` calls. Running weekly keeps it well within the free [[Constraints|rate limit]]; the live 5-min poll stays cheap because it only touches the small curated watchlist.

## Config keys
- `watchlist` — comma-separated item IDs (curator output; editable in the dashboard Settings panel)
- `curate_strategy` — which strategy ranks candidates (default `mean_reversion`)
- `curate_budget` — gp budget used during backtest scoring
- `curate_interval_days` — shown/edited in Settings (cadence governed by the scheduler's `curate_interval_s`)

## Dashboard
The Settings panel shows the watchlist + curate interval; `GET /api/watchlist` returns the current list.
