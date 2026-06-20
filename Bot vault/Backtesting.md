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

## Honest assumptions
GE data has no order-book depth, so fills are assumed. Backtest uses conservative assumptions — partial fills, GE buy limits, [[GE Tax and PL|2% tax]] — so results don't lie. **Backtest is guidance, not gospel.**

## Compares
[[mean_reversion]] · [[bollinger]] · [[rsi]] · [[crash_recovery]] · [[ma_crossover]] · [[momentum]] · [[breakout]] · [[margin_flip]]

The two families ([[Strategy System|mean-reversion vs trend]]) win in different market conditions, so the winner can vary per item category.

Built in [[Build Phases|Phase 5]].
