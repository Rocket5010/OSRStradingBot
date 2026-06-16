# Strategy System

Strategies are **plugins**. Drop a `.py` file in `strategies/`, select it in the dashboard. No code changes elsewhere — the backend calls only the contract.

## Contract (`strategies/base.py`)
```python
class Strategy:
    name: str            # shown in dashboard dropdown
    description: str
    def find_buys(self, market, capital) -> list[BuySignal]: ...
    def should_sell(self, position, market) -> SellDecision: ...
    def default_params(self) -> dict: ...   # tunable in dashboard
```

## How it loads
`strategy_loader.py` ([[Modules]]) auto-discovers every file in `strategies/` at startup → populates the dashboard dropdown. Params tunable per strategy in the dashboard.

## Manual start/stop + per-strategy budget
Strategies are **started manually** by the user — nothing runs by default. When starting a strategy the user enters the **gp budget** allocated to it. The strategy may only propose buys within its own budget. Multiple strategies can run at once, each with its own allocation. Running strategies + their budgets are stored as [[Data Model|strategy_runs]].

Currently only an investing strategy is started. [[margin_flip|Flipping]] is started by the user when actively playing.

## Why pure functions
Strategies do no I/O → testable in isolation and reusable by [[Backtesting]] against historical data.

## Sell logic (hybrid, all strategies)
target margin + **stop-loss** + **max hold time**. See [[Position Lifecycle]].

## The roster
**Active flipping:** [[margin_flip]]
**Mean-reversion family** (sideways markets): [[mean_reversion]] · [[bollinger]] · [[rsi]] · [[crash_recovery]]
**Trend/momentum family** (trending markets): [[ma_crossover]] · [[momentum]] · [[breakout]]

Each running strategy gets an explicit gp budget set by the user at start (no auto-split). See [[Bond Goal]].
