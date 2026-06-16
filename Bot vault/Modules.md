# Modules

Each unit has one responsibility and is testable in isolation. Part of [[Architecture Overview]].

| Module | Responsibility | Depends on |
|---|---|---|
| `api_client.py` | Fetch from [[OSRS Wiki API]], cache, rate-limit | — |
| `poller.py` | Run every 5 min, feed strategy | api_client |
| `strategies/base.py` | [[Strategy System|Strategy interface]] + signal types | — |
| `strategy_loader.py` | Auto-discover + load strategies from folder | base |
| `strategy/*` | Individual strategies (pure, no I/O) | base |
| `positions.py` | [[Position Lifecycle]] + [[GE Tax and PL\|P/L]] | db |
| `db.py` | SQLite ([[Data Model]]) | — |
| `notify.py` | Notifications (pluggable: Discord/Telegram) | — |
| `web.py` | FastAPI: JSON API + serve dashboard | all above |
| `static/` | dashboard.html/css/js — presentation only | JSON API only |

## Notes
- `strategy/*` = **pure functions, no I/O** → trivially testable and [[Backtesting|backtestable]].
- `static/` isolated → tinker with looks freely. See [[Conventions]].
