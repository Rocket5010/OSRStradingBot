# Architecture Overview

One Python process (`app.py`). See [[Modules]] for each unit.

```
Poller (async, every 5m) ──▶ OSRS Wiki API   [[OSRS Wiki API]]
        │ raw prices + volume
        ▼
Strategy (pure functions) ◀──▶ SQLite ◀──▶ Position manager
        │ signals                              [[Position Lifecycle]]
        ▼
FastAPI (JSON API) ──▶ Notifier (Discord/Telegram)
        │ HTTP/JSON
        ▼
Dashboard (HTML/CSS/JS — presentation only)
```

## Key principle: frontend ⟂ backend
Frontend and backend talk **only** via a JSON API. The dashboard is pure presentation — restyling touches only `static/`, never backend logic. Theme via CSS variables. See [[Conventions]].

## Why one process
[[Constraints|Free-only]] + single user → minimal moving parts. Easy to run, easy to move to a free VM (see [[Launch]]).

## Related
- [[Modules]] · [[Data Model]] · [[Strategy System]] · [[Build Phases]]
