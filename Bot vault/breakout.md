# breakout

**Family:** trend/momentum. Part of the [[Strategy System]].

## Buy
Price breaks above an N-day high **with a volume spike**.

## Sell
Trailing stop (lock in gains as it climbs, exit on pullback).

## Params
`channel_days, vol_mult, trail_pct`

## Notes
Catches the start of a run. Volume confirms the break is real. Compared in [[Backtesting]].
