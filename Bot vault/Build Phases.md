# Build Phases

Build the whole thing to completion — no early MVP. Phases are a dependency order, not a stopping point. See [[Architecture Overview]] + [[Modules]].

1. **Core engine** — `api_client` (incl. [[OSRS Wiki API|/timeseries]]), `db` (full [[Data Model]]), `strategies/base`, `strategy_loader`, `poller`.
2. **Strategies** — all of them: [[margin_flip]] + investing ([[mean_reversion]] · [[bollinger]] · [[rsi]] · [[crash_recovery]] · [[ma_crossover]] · [[momentum]] · [[breakout]]). See [[Strategy System]].
3. **Backtest engine** — [[Backtesting]]: run the contract over history, rank strategies.
4. **Web backend** — `web.py` JSON API; `positions.py` + [[Position Lifecycle|state machine]]; manual start + [[Strategy System|per-strategy budget]].
5. **Dashboard** — `static/` from the mockup; strategy start/stop + budget input; accept/sell/cancel wired to API; live refresh; [[Bond Goal|bond tracker]]; backtest view.
6. **Polish** — [[Launch|one-click launcher]] + auto-start; `notify.py`.

**Later (not now):** move to Oracle Cloud Free VM ([[Launch]]).
