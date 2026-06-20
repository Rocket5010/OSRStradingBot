# Backtesting

Find the best strategy before trusting it with gp.

## How
Runs the [[Strategy System|Strategy contract]] against [[OSRS Wiki API|/timeseries]] history (24h step → up to ~1 year). Because strategies are pure functions, the same code runs live and in backtest.

## Report
Per strategy: **risk-adjusted gp/day (score), profit/day, total profit, hit rate, max drawdown**.

## Ranking metric
Strategies and curation picks are ranked by **risk-adjusted gp/day**, not raw profit:

`score = profit_per_day / (1 + max_drawdown)`   where `profit_per_day = total_profit / days`.

Raw summed profit is budget-dependent, biased by how many items are in the basket, and ignores time and risk — a strategy that earns 5M over 300 days would outrank one earning 4M over 30 days, which is wrong for the [[Bond Goal|bond goal]] (gp/day). The score time-normalizes and penalizes drawdown, so the [[Auto-pilot]] picks the steadiest earner. `rank_over_items` sums the per-item score across the basket; `curate` ranks items by the same score.

`run_backtest` also takes `max_hold_steps` (default 30 in curation/ranking) so a strategy that buys and never sells is force-closed and judged on a realistic holding period instead of being flattered by end-of-window liquidation.

## Parameter tuning (walk-forward)
`rank_over_items(tune=True)` walk-forward-tunes each strategy before ranking (module `bot/tuning.py`). Picking params that look best over the *whole* history over-fits noise; instead each item's candles are cut into disjoint contiguous time segments (blocked cross-validation) and every param combo is scored on each segment **without ever fitting to it**. A combo wins only if it earns consistently across segments — that generalizes.

The objective is deliberately **conservative** (smaller margin, higher chance, not aggressive): a combo must be profitable in at least `POS_FRACTION_GATE` (0.6) of scored windows to be eligible, then ranks by mean `conservative_score = profit_per_day * hit_rate / (1 + 2*max_drawdown)`. So steady, high-probability params beat big-but-rare ones. Grids (`tuning.GRIDS`) are small and lean conservative (take profit sooner, tighter stops, calmer bands).

Tuned params ride along in each ranking row (`params`), are stored with the ranking, and the [[Auto-pilot]] runs the winning strategy with them (`runs.ensure_auto_run(..., params)`). Live validated: tuning rescued `breakout` to +25k gp/day at 85% win / 3% drawdown, and pulled the aggressive `crash_recovery` back to the steadier `drop_pct=0.25` that's reliable across every fold.

## Honest assumptions
GE data has no order-book depth, so fills are assumed. Backtest uses conservative assumptions — volume cap, GE buy limits, [[GE Tax and PL|2% tax]] — so results don't lie. **Backtest is guidance, not gospel.**

### GE 4h buy limits
`run_backtest(buy_limit=, candle_hours=24)` models the GE 4h limit. A 24h candle spans `24/4 = 6` limit windows, so the most you can accumulate in one candle is `buy_limit * 6`. `backtest_rank.buy_limits(client)` pulls the per-item limit from [[OSRS Wiki API|/mapping]] (tolerant of stub clients → `{}`), and both `rank_over_items` and `curate` pass it in. This stops the backtest from over-buying thin, low-limit expensive items it could never actually accumulate live.

## Compares
[[mean_reversion]] · [[bollinger]] · [[rsi]] · [[crash_recovery]] · [[ma_crossover]] · [[momentum]] · [[breakout]] · [[margin_flip]]

The two families ([[Strategy System|mean-reversion vs trend]]) win in different market conditions, so the winner can vary per item category.

Built in [[Build Phases|Phase 5]].
