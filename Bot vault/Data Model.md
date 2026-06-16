# Data Model

SQLite, owned by `db.py` (see [[Modules]]).

## Tables

```
positions
  id, item_id, item_name, strategy,
  state            -- see [[Position Lifecycle]]
  buy_price, qty, buy_tax,
  sell_target, stop_loss, max_hold_until,
  sell_price, realized_pl,
  created_at, filled_at, closed_at

signals            -- log of every proposal (history/analysis)
  id, item_id, strategy, type(buy|sell),
  price, margin, roi, reason, created_at, status(shown|accepted|dismissed)

strategy_runs      -- a started strategy with its own gp budget
  id, strategy, params_json,
  budget_gp,         -- user-set at start
  spent_gp,          -- committed to open positions
  state(running|stopped),
  started_at, stopped_at

config             -- key/value: total capital, poll cadence,
                   -- [[Bond Goal]] settings, notification webhook

price_cache        -- last API snapshot (survives restart)
  item_id, low, high, vol_1h, ts
```

## Related
- [[Position Lifecycle]] — how `state` moves
- [[GE Tax and PL]] — how `realized_pl` is computed
- [[Strategy System]] — what writes to `signals`
