# rsi

**Family:** mean-reversion. Part of the [[Strategy System]].

## Buy
RSI < 30 (oversold).

## Sell
RSI > 70 (overbought). Stop-loss below.

## Params
`rsi_period, lo (30), hi (70), stop_loss_pct, max_hold_days`

## Notes
Momentum oscillator used as a reversion signal. Compared in [[Backtesting]].
