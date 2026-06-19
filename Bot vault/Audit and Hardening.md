# Audit and Hardening (2026-06-19)

Full code audit of the OSRS Flip Bot and the fixes that followed. Part of
[[Home]]. All fixes shipped with tests; suite at **156 passing**.

## High — fixed
- **H1 `database is locked`** — `db.connect` now sets `PRAGMA busy_timeout=5000`
  in addition to WAL, so concurrent writes (API + scheduler + curation) wait
  instead of erroring. See [[Architecture Overview]].
- **H2 watchlist crash** — `curator.get_watchlist` skips non-numeric tokens; a
  bad value in the [[Watchlist Curator|watchlist]] config no longer kills the
  scheduler tick every cycle.
- **H3 curate spam** — `/api/curate` + the runner are guarded by a non-blocking
  lock; repeated clicks can't spawn overlapping curation threads that hammer the
  [[OSRS Wiki API]].

## Medium — fixed
- **M1 strategy reload** — `engine_live` caches strategy prototypes per loader
  instead of re-importing all strategy files on every call (perf on weak CPUs).
- **M2 silent failures** — scheduler now logs errors (`bot.scheduler` logger)
  instead of `except: pass`; `main` configures basic logging.
- **M3 rate limit** — one shared, thread-safe `WikiClient` (lock in `_get`) is
  used by both the scheduler and the curation thread, keeping requests global.
- **M4 curation blocks loop** — periodic curation runs in its own thread +
  connection (`db_path`) so a slow network can't stall polling.
- **M5 profit number** — `/api/overview` reports `period_profit = 0` until a
  goal period is set, instead of counting all-time history. See [[Bond Goal]].
- **M6 connection leak** — the curation runner closes its temporary connection.

## Low — fixed
- **L1 input validation** — API rejects non-positive budget/price/qty (HTTP 422).
- **L4 launcher** — `start-bot.bat` redirects to `bot.log` so startup errors are
  visible (pythonw otherwise discards them). See [[Launch]].
- **L5 dependencies** — `requirements.txt` is version-bounded for reproducible
  installs.

## Known-low, intentionally left
- `set_config` accepts arbitrary keys (flexible; dashboard only writes known
  ones).
- `_transition` re-reads the position (a TOCTOU window) — negligible for a
  single-user local app.

## Confirmed solid
Money math (P/L, GE tax, capital commit/release), the [[Position Lifecycle]]
state machine, position-scoped sell-signal de-dup, stale-proposal auto-expiry,
and separate DB connections per thread.
