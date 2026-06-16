# crash_recovery

**Family:** mean-reversion. Part of the [[Strategy System]].

## Buy
Price dropped > X% but has a **stable historical floor** — an overreaction to a game update/nerf.

## Sell
Recovery back toward the floor/normal. Stop-loss if the floor breaks (real devaluation, not overreaction).

## Params
`drop_pct, floor_lookback, stop_loss_pct, max_hold_days`

## Notes
Event-driven edge unique to OSRS. Evaluated in [[Backtesting]].
