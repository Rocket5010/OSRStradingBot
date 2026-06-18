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
