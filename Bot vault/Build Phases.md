# Build Phases

Build the whole thing to completion — no early MVP. Phases are a dependency order, not a stopping point. See [[Architecture Overview]] + [[Modules]].

1. ✅ **Core engine** — `api_client` (incl. [[OSRS Wiki API|/timeseries]]), `db` (full [[Data Model]]), `strategies/base`, `strategy_loader`, `poller`.
2. ✅ **Strategies** — all 8: [[margin_flip]] + investing ([[mean_reversion]] · [[bollinger]] · [[rsi]] · [[crash_recovery]] · [[ma_crossover]] · [[momentum]] · [[breakout]]). See [[Strategy System]].
3. ✅ **Backtest engine** — [[Backtesting]]: run the contract over history, rank strategies.
4. ✅ **Web backend (4a)** — `web.py` JSON API; `positions.py` + [[Position Lifecycle|state machine]]; manual start + [[Strategy System|per-strategy budget]].
   ✅ **Live engine (4b)** — `market.py` (assemble MarketData + cached `/timeseries`), `engine_live.py` (proposals within budget + sell recs), `scheduler.py` (5-min daemon thread, own db conn), `main.py`.
5. ⏳ **Dashboard** — `static/` from the mockup; strategy start/stop + budget input; accept/sell/cancel wired to API; live refresh; [[Bond Goal|bond tracker]]; backtest view. **← NEXT**
6. ⏳ **Polish** — [[Launch|one-click launcher]] + auto-start; `notify.py`.

**Later (not now):** move to Oracle Cloud Free VM ([[Launch]]).

## Status (2026-06-17)
Phases 1–4 complete. **118 tests passing**, all pushed to GitHub. The "brain" runs end-to-end against live OSRS data: polls prices, runs strategies within budget, proposes buys, recommends sells. Remaining: Phase 5 (dashboard UI) + Phase 6 (launcher + notifications).
