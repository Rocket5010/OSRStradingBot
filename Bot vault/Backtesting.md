# Backtesting

Find the best strategy before trusting it with gp.

## How
Runs the [[Strategy System|Strategy contract]] against [[OSRS Wiki API|/timeseries]] history (24h step → up to ~1 year). Because strategies are pure functions, the same code runs live and in backtest.

## Report
Per strategy: **profit, hit rate, max drawdown**.

## Honest assumptions
GE data has no order-book depth, so fills are assumed. Backtest uses conservative assumptions — partial fills, GE buy limits, [[GE Tax and PL|2% tax]] — so results don't lie. **Backtest is guidance, not gospel.**

## Compares
[[mean_reversion]] · [[bollinger]] · [[rsi]] · [[crash_recovery]] · [[ma_crossover]] · [[momentum]] · [[breakout]] · [[margin_flip]]

The two families ([[Strategy System|mean-reversion vs trend]]) win in different market conditions, so the winner can vary per item category.

Built in [[Build Phases|Phase 5]].
