# Build Phases

Build the whole thing to completion — no early MVP. Phases are a dependency order, not a stopping point. See [[Architecture Overview]] + [[Modules]].

1. ✅ **Core engine** — `api_client` (incl. [[OSRS Wiki API|/timeseries]]), `db` (full [[Data Model]]), `strategies/base`, `strategy_loader`, `poller`.
2. ✅ **Strategies** — all 8: [[margin_flip]] + investing ([[mean_reversion]] · [[bollinger]] · [[rsi]] · [[crash_recovery]] · [[ma_crossover]] · [[momentum]] · [[breakout]]). See [[Strategy System]].
3. ✅ **Backtest engine** — [[Backtesting]]: run the contract over history, rank strategies.
4. ✅ **Web backend (4a)** — `web.py` JSON API; `positions.py` + [[Position Lifecycle|state machine]]; manual start + [[Strategy System|per-strategy budget]].
   ✅ **Live engine (4b)** — `market.py` (assemble MarketData + cached `/timeseries`), `engine_live.py` (proposals within budget + sell recs), `scheduler.py` (5-min daemon thread, own db conn), `main.py`.
5. ✅ **Dashboard** — `bot/static/` (index.html + style.css + app.js) dark+gold UI; strategy start/stop + budget input; buy-signal + position tables with accept/fill/sell/sold/cancel/dismiss; `/api/overview` + [[Bond Goal|bond tracker]]; 5s live refresh. Served by FastAPI.
6. ⏳ **Polish** — [[Launch|one-click launcher]] + auto-start; `notify.py`; bond_price/goal-period config refresh. **← NEXT**

**Later (not now):** move to Oracle Cloud Free VM ([[Launch]]).

## Status (2026-06-17)
Phases 1–5 complete. **123 tests passing**, all pushed to GitHub. The "brain" runs end-to-end against live OSRS data and the dark+gold dashboard (`python -m bot.main` → http://127.0.0.1:8000) renders it. Remaining: Phase 6 (launcher + notifications + bond-price config refresh).
