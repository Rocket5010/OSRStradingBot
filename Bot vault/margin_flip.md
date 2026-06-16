# margin_flip

**Family:** active flipping. Part of the [[Strategy System]].

## Buy
`margin = high − [[GE Tax and PL|tax]] − low > min_margin` AND `vol_1h > min_vol` AND `roi > min_roi`. Sized against free capital + GE buy limit.

## Sell
At `sell_target` (buy + target margin). Stop-loss at −X%. Short max hold (hours).

## Params
`min_margin, min_vol, min_roi, target_pct, stop_loss_pct, max_hold_hours`

## Notes
This is the logic already proven in the `flip_finder.py` MVP. First strategy built ([[Build Phases|Phase 1]]).
