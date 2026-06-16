# Bond Goal

The success metric: **one bond every 14 days**.

Bond (item id 13190) live price ≈ **14M gp** (fetched via [[OSRS Wiki API]]). That means a target of **~1M gp/day net profit** (after [[GE Tax and PL|tax]]).

## Tracker
Dashboard shows a progress bar: `earned this period / bond price`. Bond price updates live, so the target self-adjusts. Stored in [[Data Model|config]].

## Drives
The user sizes each [[Strategy System|strategy budget]] to aim at this rate without freezing gp in dead positions ([[Position Lifecycle|max hold time]]).
