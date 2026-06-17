# Build Phases

Build the whole thing to completion — no early MVP. Phases are a dependency order, not a stopping point. See [[Architecture Overview]] + [[Modules]].

1. ✅ **Core engine** — `api_client` (incl. [[OSRS Wiki API|/timeseries]]), `db` (full [[Data Model]]), `strategies/base`, `strategy_loader`, `poller`.
2. ✅ **Strategies** — all 8: [[margin_flip]] + investing ([[mean_reversion]] · [[bollinger]] · [[rsi]] · [[crash_recovery]] · [[ma_crossover]] · [[momentum]] · [[breakout]]). See [[Strategy System]].
3. ✅ **Backtest engine** — [[Backtesting]]: run the contract over history, rank strategies.
4. ✅ **Web backend (4a)** — `web.py` JSON API; `positions.py` + [[Position Lifecycle|state machine]]; manual start + [[Strategy System|per-strategy budget]].
   ✅ **Live engine (4b)** — `market.py` (assemble MarketData + cached `/timeseries`), `engine_live.py` (proposals within budget + sell recs), `scheduler.py` (5-min daemon thread, own db conn), `main.py`.
5. ✅ **Dashboard** — `bot/static/` (index.html + style.css + app.js) dark+gold UI; strategy start/stop + budget input; buy-signal + position tables with accept/fill/sell/sold/cancel/dismiss; `/api/overview` + [[Bond Goal|bond tracker]]; 5s live refresh. Served by FastAPI.
6. ✅ **Polish** — [[Launch|one-click launcher]] (`start-bot.bat`) + auto-start docs; `notify.py` (webhook); `goal.py` bond-price/goal-period refresh wired into the scheduler.

**Later (not now):** move to Oracle Cloud Free VM ([[Launch]]).

## Status (2026-06-17) — FEATURE COMPLETE
All 6 phases done. **131 tests passing**, all pushed to GitHub. End-to-end: polls live OSRS prices → runs strategies within per-run budget → proposes buys / recommends sells → dark+gold dashboard + optional webhook notifications → bond-goal tracker. Run: `start-bot.bat` (or `python -m bot.main`) → http://127.0.0.1:8000. Remaining is operational only: move to an always-on Oracle Cloud Free VM ([[Launch]]) when desired.
