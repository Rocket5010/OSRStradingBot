# Position Lifecycle

State machine for a position. Stored in [[Data Model|positions.state]], managed by `positions.py` ([[Modules]]).

```
proposed ──accept──▶ accepted ──fill──▶ filled ──sell-signal──▶ selling ──fill──▶ sold
   │                    │                                          │
   └──dismiss──▶ dismissed └──withdraw──▶ cancelled    cancel──────┘
```

## Who drives it
The user drives transitions via dashboard buttons ([[Constraints|bot = brain, user = hand]]). The bot **proposes** `filled`/`selling` transitions; the user confirms when the GE order actually fills.

## States
- **proposed** — bot suggested a buy ([[Strategy System|find_buys]])
- **accepted** — user placed the GE buy order
- **filled** — order filled, now holding
- **selling** — bot signaled sell ([[Strategy System|should_sell]]), user placed sell order
- **sold** — closed, [[GE Tax and PL|realized_pl]] recorded
- **cancelled** — order withdrawn (didn't fill)
- **dismissed** — user rejected the proposal

## Auto-expiry of stale proposals
Each evaluation pass the live engine re-checks every `proposed` position: it asks
the strategy whether it still wants that item at the current market (via
`find_buys` with an unbounded budget so only the signal criteria matter). If the
signal is gone — price moved, indicator flipped — the proposal is auto-`dismissed`
so the buy list never shows opportunities that are no longer worth it. Proposals
for items with no fresh market data are left untouched.

## Why cancel/withdraw exists
GE orders don't always fill. The user can withdraw an unfilled buy or sell.

## Stale-order flagging (frozen capital)
The bot never auto-cancels (it can't see your GE order, and it might be mid-fill),
but it surfaces orders that aren't filling so capital doesn't silently freeze.
`accept` stamps `accepted_at`; `/api/positions` returns `age_hours` and a `stale`
flag for **pending** states (`accepted`, `selling`) older than `order_stale_hours`
(config, default 24). The dashboard marks them ⚠ and `/api/overview` reports
`stale_orders` + `frozen_gp` (capital locked in stale orders). Capital is only
released on `mark_sold`/`cancel`, so a dead order starves the budget until you act
— the flag is the reminder to cancel or re-price (undercut/overcut).
