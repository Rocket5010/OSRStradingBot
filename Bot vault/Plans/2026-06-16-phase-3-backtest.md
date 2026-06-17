# Phase 3 — Backtest Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> Index: [[Home]] · Spec: [[OSRS Flip Bot Design Spec]] · Phases: [[Build Phases]] · Prev: [[2026-06-16-phase-2-strategies]]

**Goal:** Run any Phase 2 strategy over historical `/timeseries` candles with conservative fill assumptions, measure profit / hit-rate / max-drawdown, and rank all strategies head-to-head to find the best one.

**Architecture:** `bot/tax.py` holds the shared GE-tax function (extracted from `margin_flip`, single source). `bot/backtest/metrics.py` computes performance metrics from trades + an equity curve. `bot/backtest/engine.py` walks candle-by-candle: build a `MarketData` snapshot of history-so-far, run the strategy's buy/sell decisions, simulate fills (buy at `avgLow`, sell at `avgHigh` minus tax), and enforce a uniform max-hold. `bot/backtest/ranking.py` runs all strategies over the same data and sorts by profit. `bot/backtest/runner.py` fetches real candles via the Phase 1 `WikiClient` and produces a ranking (network isolated behind the client, tested with a stub).

**Tech Stack:** Python 3.13, stdlib only, `pytest`.

---

## File Structure

```
bot/
├── tax.py                  # ge_tax (shared)
└── backtest/
    ├── __init__.py
    ├── metrics.py          # total_profit, hit_rate, max_drawdown
    ├── engine.py           # Position, BacktestResult, run_backtest
    ├── ranking.py          # rank_strategies
    └── runner.py           # run_ranking(client, ...) — fetch + rank
tests/
├── test_tax.py
├── test_metrics.py
├── test_engine.py
├── test_ranking.py
└── test_runner.py
```

## Conventions

- A **candle** is the `/timeseries` dict: `{"timestamp", "avgHighPrice", "avgLowPrice", "highPriceVolume", "lowPriceVolume"}`. Prices may be `None` (no trades that step).
- A **trade** (closed position) is a dict: `{"pl": int, "buy_price": int, "sell_price": int, "qty": int}`.
- Fills: buy at `avgLowPrice`, sell at `avgHighPrice`. Sells pay GE tax. This is deliberately conservative (you rarely get the best price).

---

### Task 1: Extract GE tax to bot/tax.py

**Files:**
- Create: `bot/tax.py`
- Modify: `bot/strategies/margin_flip.py`
- Test: `tests/test_tax.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tax.py
from bot.tax import ge_tax


def test_two_percent_floored():
    assert ge_tax(1000) == 20
    assert ge_tax(149) == 2          # floor(2.98)


def test_capped_at_5m():
    assert ge_tax(10**9) == 5_000_000


def test_zero():
    assert ge_tax(0) == 0
```

- [ ] **Step 2: Run, verify failure**

Run: `python -m pytest tests/test_tax.py -v`
Expected: FAIL — no module `bot.tax`.

- [ ] **Step 3: Create bot/tax.py**

```python
# bot/tax.py
"""GE sell tax: 2% of sell price, floored, capped at 5M per item."""

from math import floor

TAX_RATE = 0.02
TAX_CAP = 5_000_000


def ge_tax(price):
    return min(floor(price * TAX_RATE), TAX_CAP)
```

- [ ] **Step 4: Refactor margin_flip to use it**

In `bot/strategies/margin_flip.py`, remove the local `TAX_RATE`, `TAX_CAP`, and `ge_tax` definitions and replace the import block at the top so it reads:

```python
"""Active flipping: buy items with a healthy spread after GE tax."""

from bot.strategies.base import Strategy, BuySignal, SellDecision
from bot.strategies.sizing import size_qty
from bot.tax import ge_tax
```

(The `from math import floor` line and the `TAX_RATE`/`TAX_CAP`/`ge_tax` block are deleted; the rest of the file is unchanged — `ge_tax` is now the imported one.)

- [ ] **Step 5: Run tax + margin_flip tests**

Run: `python -m pytest tests/test_tax.py tests/test_margin_flip.py -v`
Expected: PASS (tax 3 + margin_flip 7 = 10 passed).

- [ ] **Step 6: Commit**

```bash
git add bot/tax.py bot/strategies/margin_flip.py tests/test_tax.py
git commit -m "refactor: extract ge_tax to bot/tax.py"
```

---

### Task 2: Metrics

**Files:**
- Create: `bot/backtest/__init__.py` (empty), `bot/backtest/metrics.py`
- Test: `tests/test_metrics.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_metrics.py
from bot.backtest.metrics import total_profit, hit_rate, max_drawdown


def test_total_profit():
    assert total_profit([{"pl": 10}, {"pl": -5}, {"pl": 3}]) == 8


def test_total_profit_empty():
    assert total_profit([]) == 0


def test_hit_rate():
    assert hit_rate([{"pl": 10}, {"pl": -5}, {"pl": 3}]) == 2 / 3


def test_hit_rate_no_trades():
    assert hit_rate([]) == 0.0


def test_max_drawdown():
    # peak 120 then trough 90 -> (120-90)/120 = 0.25
    assert max_drawdown([100, 120, 90, 110]) == 0.25


def test_max_drawdown_monotonic_up():
    assert max_drawdown([100, 110, 120]) == 0.0


def test_max_drawdown_empty():
    assert max_drawdown([]) == 0.0
```

- [ ] **Step 2: Run, verify failure**

Run: `python -m pytest tests/test_metrics.py -v`
Expected: FAIL — no module `bot.backtest.metrics`.

- [ ] **Step 3: Implement metrics**

```python
# bot/backtest/metrics.py
"""Performance metrics for a backtest run."""


def total_profit(trades):
    return sum(t["pl"] for t in trades)


def hit_rate(trades):
    if not trades:
        return 0.0
    wins = sum(1 for t in trades if t["pl"] > 0)
    return wins / len(trades)


def max_drawdown(equity_curve):
    """Largest peak-to-trough drop as a fraction of the peak."""
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    worst = 0.0
    for v in equity_curve:
        if v > peak:
            peak = v
        if peak > 0:
            drop = (peak - v) / peak
            if drop > worst:
                worst = drop
    return worst
```

- [ ] **Step 4: Run, verify pass**

Run: `python -m pytest tests/test_metrics.py -v`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add bot/backtest/__init__.py bot/backtest/metrics.py tests/test_metrics.py
git commit -m "feat: add backtest metrics"
```

---

### Task 3: Backtest engine

**Files:**
- Create: `bot/backtest/engine.py`
- Test: `tests/test_engine.py`

Walk-forward simulation over candles for a single item. The engine sets `position.high_water` each step (for breakout) and enforces `max_hold_steps` uniformly. Sells are processed before buys each step. At the end, any open positions are liquidated at the last valid price.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_engine.py
from bot.backtest.engine import run_backtest, BacktestResult


def candle(hi, lo, vol=1000):
    return {"avgHighPrice": hi, "avgLowPrice": lo,
            "highPriceVolume": vol, "lowPriceVolume": vol}


class BuyOnceSellHigh:
    """Stub: buys 1 unit on the first opportunity, sells when high >= 120."""
    name = "stub"

    def __init__(self):
        self.bought = False

    def find_buys(self, markets, budget):
        from bot.strategies.base import BuySignal
        m = markets[0]
        if self.bought or budget < m.low:
            return []
        self.bought = True
        return [BuySignal(item_id=m.item_id, price=m.low, qty=1, reason="stub")]

    def should_sell(self, position, market):
        from bot.strategies.base import SellDecision
        return SellDecision(sell=market.high >= 120, reason="stub")


def test_buy_then_sell_profit_after_tax():
    # buy at low=100 on candle 0; candle 1 high=120 triggers sell.
    candles = [candle(hi=105, lo=100), candle(hi=120, lo=118)]
    res = run_backtest(BuyOnceSellHigh(), candles, budget=1000)
    assert isinstance(res, BacktestResult)
    assert res.n_trades == 1
    # sell at 120, tax = floor(120*0.02)=2, proceeds=118, cost=100 -> pl=18
    assert res.trades[0]["pl"] == 18
    assert res.total_profit == 18


def test_skips_none_price_candles():
    candles = [{"avgHighPrice": None, "avgLowPrice": None,
                "highPriceVolume": 0, "lowPriceVolume": 0},
               candle(hi=105, lo=100), candle(hi=120, lo=118)]
    res = run_backtest(BuyOnceSellHigh(), candles, budget=1000)
    assert res.n_trades == 1


def test_max_hold_forces_close():
    # never hits sell signal (high stays < 120); max_hold_steps=1 forces close.
    candles = [candle(hi=105, lo=100), candle(hi=106, lo=104), candle(hi=107, lo=105)]
    res = run_backtest(BuyOnceSellHigh(), candles, budget=1000, max_hold_steps=1)
    assert res.n_trades == 1  # forced close, not left open


def test_open_position_liquidated_at_end():
    candles = [candle(hi=105, lo=100), candle(hi=106, lo=104)]
    res = run_backtest(BuyOnceSellHigh(), candles, budget=1000)
    assert res.n_trades == 1  # closed via end-of-data liquidation
```

- [ ] **Step 2: Run, verify failure**

Run: `python -m pytest tests/test_engine.py -v`
Expected: FAIL — no module `bot.backtest.engine`.

- [ ] **Step 3: Implement engine**

```python
# bot/backtest/engine.py
"""Walk-forward backtest of a strategy over historical candles."""

from dataclasses import dataclass, field

from bot.strategies.base import MarketData
from bot.tax import ge_tax
from bot.backtest.metrics import total_profit, hit_rate, max_drawdown


@dataclass
class Position:
    item_id: int
    buy_price: int
    qty: int
    high_water: int
    open_index: int
    ref_price: int = None


@dataclass
class BacktestResult:
    total_profit: int
    n_trades: int
    hit_rate: float
    max_drawdown: float
    final_equity: int
    trades: list = field(default_factory=list)


def _close(pos, sell_price):
    proceeds = (sell_price - ge_tax(sell_price)) * pos.qty
    cost = pos.buy_price * pos.qty
    return {"pl": proceeds - cost, "buy_price": pos.buy_price,
            "sell_price": sell_price, "qty": pos.qty}


def run_backtest(strategy, candles, budget, item_id=1, name="item",
                 buy_limit=0, members=False, max_hold_steps=None):
    cash = budget
    open_positions = []
    trades = []
    equity_curve = []
    last_high = None

    for i, c in enumerate(candles):
        hi, lo = c.get("avgHighPrice"), c.get("avgLowPrice")
        if hi is None or lo is None:
            equity_curve.append(cash + sum(
                (last_high - ge_tax(last_high)) * p.qty for p in open_positions
            ) if last_high else cash)
            continue
        last_high = hi
        vol = (c.get("highPriceVolume") or 0) + (c.get("lowPriceVolume") or 0)
        md = MarketData(item_id=item_id, name=name, low=lo, high=hi, vol_1h=vol,
                        history=candles[:i + 1], buy_limit=buy_limit, members=members)

        # sells first
        for pos in list(open_positions):
            pos.high_water = max(pos.high_water, hi)
            forced = max_hold_steps is not None and (i - pos.open_index) >= max_hold_steps
            decision = strategy.should_sell(pos, md)
            if decision.sell or forced:
                trades.append(_close(pos, hi))
                cash += (hi - ge_tax(hi)) * pos.qty
                open_positions.remove(pos)

        # buys
        for sig in strategy.find_buys([md], cash):
            cost = sig.price * sig.qty
            if cost > cash:
                continue
            cash -= cost
            open_positions.append(Position(item_id=item_id, buy_price=sig.price,
                                           qty=sig.qty, high_water=hi, open_index=i))

        equity_curve.append(cash + sum(
            (hi - ge_tax(hi)) * p.qty for p in open_positions))

    # liquidate any remaining positions at the last valid high
    if last_high is not None:
        for pos in list(open_positions):
            trades.append(_close(pos, last_high))
            cash += (last_high - ge_tax(last_high)) * pos.qty
            open_positions.remove(pos)

    return BacktestResult(
        total_profit=total_profit(trades),
        n_trades=len(trades),
        hit_rate=hit_rate(trades),
        max_drawdown=max_drawdown(equity_curve),
        final_equity=cash,
        trades=trades,
    )
```

- [ ] **Step 4: Run, verify pass**

Run: `python -m pytest tests/test_engine.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add bot/backtest/engine.py tests/test_engine.py
git commit -m "feat: add walk-forward backtest engine"
```

---

### Task 4: Strategy ranking

**Files:**
- Create: `bot/backtest/ranking.py`
- Test: `tests/test_ranking.py`

`rank_strategies` runs each strategy over the same candles and returns `(name, BacktestResult)` tuples sorted by `total_profit` descending. A fresh strategy instance is used per run (strategies may hold state), so callers pass a dict of `{name: factory}` where factory is a zero-arg callable returning a strategy.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ranking.py
from bot.backtest.ranking import rank_strategies
from bot.strategies.base import BuySignal, SellDecision


def candle(hi, lo):
    return {"avgHighPrice": hi, "avgLowPrice": lo,
            "highPriceVolume": 1000, "lowPriceVolume": 1000}


class Profitable:
    name = "profitable"
    def __init__(self): self.bought = False
    def find_buys(self, markets, budget):
        m = markets[0]
        if self.bought or budget < m.low: return []
        self.bought = True
        return [BuySignal(item_id=m.item_id, price=m.low, qty=1, reason="")]
    def should_sell(self, position, market):
        return SellDecision(sell=market.high >= 200, reason="")


class DoesNothing:
    name = "nothing"
    def find_buys(self, markets, budget): return []
    def should_sell(self, position, market): return SellDecision(sell=False, reason="")


def test_ranks_by_profit():
    candles = [candle(100, 100), candle(200, 190)]
    factories = {"profitable": Profitable, "nothing": DoesNothing}
    ranked = rank_strategies(factories, candles, budget=1000)
    assert [name for name, _ in ranked] == ["profitable", "nothing"]
    assert ranked[0][1].total_profit > 0
    assert ranked[1][1].total_profit == 0
```

- [ ] **Step 2: Run, verify failure**

Run: `python -m pytest tests/test_ranking.py -v`
Expected: FAIL — no module `bot.backtest.ranking`.

- [ ] **Step 3: Implement ranking**

```python
# bot/backtest/ranking.py
"""Run multiple strategies over the same candles and rank by profit."""

from bot.backtest.engine import run_backtest


def rank_strategies(factories, candles, budget, **kwargs):
    """factories: {name: zero-arg callable -> Strategy}. Returns list of
    (name, BacktestResult) sorted by total_profit descending."""
    results = []
    for name, factory in factories.items():
        result = run_backtest(factory(), candles, budget, **kwargs)
        results.append((name, result))
    results.sort(key=lambda pair: pair[1].total_profit, reverse=True)
    return results
```

- [ ] **Step 4: Run, verify pass**

Run: `python -m pytest tests/test_ranking.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add bot/backtest/ranking.py tests/test_ranking.py
git commit -m "feat: add strategy ranking"
```

---

### Task 5: Runner — fetch real candles and rank

**Files:**
- Create: `bot/backtest/runner.py`
- Test: `tests/test_runner.py`

`run_ranking` fetches `/timeseries` candles for one item via the Phase 1 `WikiClient`, then ranks the supplied strategy factories. Network is isolated behind the client, so the test uses a stub client (no network). A thin `__main__`-style `main()` is included for manual use but is not unit-tested.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_runner.py
from bot.backtest.runner import run_ranking
from bot.strategies.base import BuySignal, SellDecision


class StubClient:
    def __init__(self, candles):
        self._candles = candles
        self.requested = []
    def timeseries(self, item_id, timestep):
        self.requested.append((item_id, timestep))
        return self._candles


class Profitable:
    name = "profitable"
    def __init__(self): self.bought = False
    def find_buys(self, markets, budget):
        m = markets[0]
        if self.bought or budget < m.low: return []
        self.bought = True
        return [BuySignal(item_id=m.item_id, price=m.low, qty=1, reason="")]
    def should_sell(self, position, market):
        return SellDecision(sell=market.high >= 200, reason="")


def test_run_ranking_fetches_and_ranks():
    candles = [{"avgHighPrice": 100, "avgLowPrice": 100,
                "highPriceVolume": 1000, "lowPriceVolume": 1000},
               {"avgHighPrice": 200, "avgLowPrice": 190,
                "highPriceVolume": 1000, "lowPriceVolume": 1000}]
    client = StubClient(candles)
    ranked = run_ranking(client, item_id=2, factories={"profitable": Profitable},
                         budget=1000, timestep="24h")
    assert client.requested == [(2, "24h")]
    assert ranked[0][0] == "profitable"
    assert ranked[0][1].total_profit > 0


def test_run_ranking_empty_history_returns_zero_trades():
    client = StubClient([])
    ranked = run_ranking(client, item_id=2, factories={"profitable": Profitable},
                         budget=1000, timestep="24h")
    assert ranked[0][1].n_trades == 0
```

- [ ] **Step 2: Run, verify failure**

Run: `python -m pytest tests/test_runner.py -v`
Expected: FAIL — no module `bot.backtest.runner`.

- [ ] **Step 3: Implement runner**

```python
# bot/backtest/runner.py
"""Fetch historical candles via the Wiki client and rank strategies."""

from bot.backtest.ranking import rank_strategies


def run_ranking(client, item_id, factories, budget, timestep="24h", **kwargs):
    """Fetch /timeseries for one item and rank the given strategy factories."""
    candles = client.timeseries(item_id, timestep)
    return rank_strategies(factories, candles, budget, item_id=item_id, **kwargs)


def format_ranking(ranked):
    """Return a printable table string from rank_strategies output."""
    lines = [f"{'Strategy':<16}{'Profit':>12}{'Trades':>8}{'Hit%':>7}{'MaxDD%':>8}"]
    lines.append("-" * len(lines[0]))
    for name, r in ranked:
        lines.append(f"{name:<16}{r.total_profit:>12,}{r.n_trades:>8}"
                     f"{r.hit_rate * 100:>6.0f}%{r.max_drawdown * 100:>7.1f}%")
    return "\n".join(lines)
```

- [ ] **Step 4: Run, verify pass**

Run: `python -m pytest tests/test_runner.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest`
Expected: PASS — all Phase 1 + 2 + 3 tests green.

- [ ] **Step 6: Commit**

```bash
git add bot/backtest/runner.py tests/test_runner.py
git commit -m "feat: add backtest runner over real timeseries"
```

---

## Self-Review Notes

- **Spec coverage ([[Backtesting]]):** walk-forward run over `/timeseries` (engine), profit + hit-rate + max-drawdown (metrics), conservative fills incl. GE tax + buy limit + max-hold (engine), rank all strategies (ranking), fetch real data behind the client (runner). Backtest-is-guidance caveat honored — fills assumed at avgLow/avgHigh.
- **Type consistency:** engine constructs `MarketData(item_id, name, low, high, vol_1h, history, buy_limit, members)` matching the Phase 2 extension. `Position` exposes `buy_price`, `high_water`, `ref_price` — the attributes `breakout`/`crash_recovery` read. Trades are `{"pl", "buy_price", "sell_price", "qty"}` consistently across `_close`, metrics, and tests. `run_backtest(strategy, candles, budget, ...)` signature is identical in engine, ranking, and runner.
- **Placeholder scan:** every code step complete; every run step has expected output.
- **Note:** `rank_strategies` takes factories (zero-arg callables) not instances, because stateful strategies (e.g. the stub, momentum's internal counters) must start fresh per run. The Phase 4 wiring must pass `lambda: StrategyClass(**params)` factories.

## Next Phase
After Phase 3 is green: write the Phase 4 plan (web backend + position manager + manual start + per-strategy budget), which wires these strategies and the live poller into the FastAPI JSON API.
