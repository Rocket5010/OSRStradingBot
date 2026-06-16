# mean_reversion

**Family:** mean-reversion (good in sideways markets). Part of the [[Strategy System]].

## Buy
`price < mean − k·σ` over a lookback window — statistically cheap.

## Sell
Back to the mean. Stop-loss if it breaks further down. Long max hold (days).

## Params
`lookback_days, k_stdev, min_vol, stop_loss_pct, max_hold_days`

## Data
Uses [[OSRS Wiki API|/timeseries]] for history. Compared against siblings in [[Backtesting]].
