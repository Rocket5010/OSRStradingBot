# bollinger

**Family:** mean-reversion. Part of the [[Strategy System]].

## Buy
Price touches the **lower Bollinger band** (mean − k·σ over `period`).

## Sell
Middle or upper band. Stop-loss below.

## Params
`period, k_bands, stop_loss_pct, max_hold_days`

## Notes
A banded variant of [[mean_reversion]]. Evaluated in [[Backtesting]].
