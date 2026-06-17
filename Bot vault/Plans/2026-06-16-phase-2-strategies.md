# Phase 2 — Strategies Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> Index: [[Home]] · Spec: [[OSRS Flip Bot Design Spec]] · Phases: [[Build Phases]] · Prev: [[2026-06-16-phase-1-core-engine]]

**Goal:** Implement all eight trading strategies as pure-function plugins against the Phase 1 `Strategy` contract — one active flipper plus seven investing strategies — backed by a shared indicators module.

**Architecture:** Strategies live in `bot/strategies/*.py`, auto-discovered by the Phase 1 loader. Each is a pure function of `MarketData` (no I/O), so it is trivially testable and reusable by the Phase 3 backtester. Shared math (SMA, stdev, RSI, Bollinger bands, price-series extraction) lives in `bot/strategies/indicators.py`. Budget sizing lives in `bot/strategies/sizing.py`. `should_sell` encodes each strategy's own exit signal plus a stop-loss; uniform max-hold enforcement is the engine's job (Phase 4), not the strategy's.

**Tech Stack:** Python 3.13, stdlib only (`statistics`, `math`), `pytest`.

---

## Conventions for every strategy file

- Subclass `Strategy` from `bot.strategies.base`.
- Class attrs `name` (matches filename stem) and `description`.
- `__init__(self, **params)`: `self.params = {**self.default_params(), **params}`.
- `find_buys(self, markets, budget)`: `markets` is `list[MarketData]`; return `list[BuySignal]` whose total cost (`price * qty`) does not exceed `budget`. Use `bot.strategies.sizing.size_qty`.
- `should_sell(self, position, market)`: `position` has at least `.buy_price` (int). Return `SellDecision`. Sell if the strategy's exit signal fires OR price has fallen to/below the stop-loss.
- `default_params(self)`: dict of tunable params.

## History candle shape

`MarketData.history` is a list of candle dicts from the Wiki `/timeseries` endpoint:
```python
{"timestamp": 1700000000, "avgHighPrice": 210, "avgLowPrice": 190,
 "highPriceVolume": 50, "lowPriceVolume": 60}
```
A candle may have `None` for `avgHighPrice`/`avgLowPrice` (no trades that step). The price series helper skips those.

---

### Task 1: Extend MarketData + sizing helper

**Files:**
- Modify: `bot/strategies/base.py`
- Create: `bot/strategies/sizing.py`
- Modify: `tests/test_base.py`
- Test: `tests/test_sizing.py`

- [ ] **Step 1: Update the MarketData test (failing)**

In `tests/test_base.py`, replace `test_marketdata_holds_fields` with:

```python
def test_marketdata_holds_fields():
    md = MarketData(item_id=2, name="Cannonball", low=150, high=200,
                    vol_1h=5000, history=[], buy_limit=11000, members=False)
    assert md.item_id == 2 and md.high == 200
    assert md.buy_limit == 11000 and md.members is False


def test_marketdata_defaults():
    md = MarketData(item_id=2, name="X", low=1, high=2, vol_1h=0)
    assert md.history == [] and md.buy_limit == 0 and md.members is False
```

- [ ] **Step 2: Run, verify failure**

Run: `python -m pytest tests/test_base.py -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'buy_limit'`.

- [ ] **Step 3: Extend the dataclass**

In `bot/strategies/base.py`, change `MarketData` to:

```python
@dataclass
class MarketData:
    item_id: int
    name: str
    low: int            # instant-buy price
    high: int           # instant-sell price
    vol_1h: int
    history: list = field(default_factory=list)   # timeseries candles, if loaded
    buy_limit: int = 0  # GE 4h buy limit
    members: bool = False
```

- [ ] **Step 4: Run, verify pass**

Run: `python -m pytest tests/test_base.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Write the sizing test (failing)**

```python
# tests/test_sizing.py
from bot.strategies.sizing import size_qty


def test_limited_by_budget():
    # budget 1000, price 100, no buy limit -> 10
    assert size_qty(price=100, budget=1000, buy_limit=0) == 10


def test_limited_by_buy_limit():
    # budget huge, price 100, buy_limit 4 -> 4
    assert size_qty(price=100, budget=10**9, buy_limit=4) == 4


def test_zero_when_cannot_afford_one():
    assert size_qty(price=100, budget=50, buy_limit=0) == 0


def test_zero_price_returns_zero():
    assert size_qty(price=0, budget=1000, buy_limit=10) == 0
```

- [ ] **Step 6: Run, verify failure**

Run: `python -m pytest tests/test_sizing.py -v`
Expected: FAIL — no module `bot.strategies.sizing`.

- [ ] **Step 7: Implement sizing**

```python
# bot/strategies/sizing.py
"""Quantity sizing for buy signals: bounded by budget and GE buy limit."""


def size_qty(price, budget, buy_limit):
    """Max units affordable within budget, capped by buy_limit (0 = no cap)."""
    if price <= 0:
        return 0
    qty = budget // price
    if buy_limit and buy_limit > 0:
        qty = min(qty, buy_limit)
    return int(qty)
```

- [ ] **Step 8: Run, verify pass**

Run: `python -m pytest tests/test_sizing.py -v`
Expected: PASS (4 passed).

- [ ] **Step 9: Commit**

```bash
git add bot/strategies/base.py bot/strategies/sizing.py tests/test_base.py tests/test_sizing.py
git commit -m "feat: extend MarketData (buy_limit, members) and add size_qty"
```

---

### Task 2: Indicators module

**Files:**
- Create: `bot/strategies/indicators.py`
- Test: `tests/test_indicators.py`

Pure math over a numeric price series. `price_series` extracts mid-prices from candles, skipping `None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_indicators.py
import pytest
from bot.strategies import indicators as ind


def test_price_series_skips_none():
    candles = [
        {"avgHighPrice": 200, "avgLowPrice": 100},   # mid 150
        {"avgHighPrice": None, "avgLowPrice": None},  # skipped
        {"avgHighPrice": 220, "avgLowPrice": 180},   # mid 200
    ]
    assert ind.price_series(candles) == [150.0, 200.0]


def test_sma_last_window():
    assert ind.sma([1, 2, 3, 4, 5], 2) == 4.5   # mean of last 2


def test_sma_none_when_too_short():
    assert ind.sma([1, 2], 5) is None


def test_mean_and_stdev():
    assert ind.mean([2, 4, 6]) == 4.0
    assert round(ind.stdev([2, 4, 6]), 4) == 2.0   # population stdev


def test_bollinger_bands():
    series = [10, 12, 14, 12, 10, 12, 14, 12, 10, 12]
    lower, mid, upper = ind.bollinger(series, period=10, k=2)
    assert round(mid, 1) == 11.8
    assert lower < mid < upper


def test_rsi_all_gains_is_100():
    series = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
    assert ind.rsi(series, period=14) == 100.0


def test_rsi_none_when_too_short():
    assert ind.rsi([1, 2, 3], period=14) is None


def test_window_high():
    assert ind.window_high([5, 9, 3, 7], 3) == 9   # max of last 3
```

- [ ] **Step 2: Run, verify failure**

Run: `python -m pytest tests/test_indicators.py -v`
Expected: FAIL — no module `bot.strategies.indicators`.

- [ ] **Step 3: Implement indicators**

```python
# bot/strategies/indicators.py
"""Pure technical indicators over a numeric price series. Stdlib only."""

import statistics


def price_series(candles):
    """Mid-price per candle; skips candles with missing prices."""
    out = []
    for c in candles:
        hi, lo = c.get("avgHighPrice"), c.get("avgLowPrice")
        if hi is None or lo is None:
            continue
        out.append((hi + lo) / 2)
    return out


def mean(series):
    return statistics.fmean(series)


def stdev(series):
    """Population standard deviation."""
    return statistics.pstdev(series)


def sma(series, window):
    """Simple moving average of the last `window` points, or None if too short."""
    if len(series) < window or window <= 0:
        return None
    return statistics.fmean(series[-window:])


def bollinger(series, period, k):
    """Return (lower, mid, upper) bands over the last `period` points."""
    if len(series) < period:
        return None
    window = series[-period:]
    mid = statistics.fmean(window)
    sd = statistics.pstdev(window)
    return (mid - k * sd, mid, mid + k * sd)


def rsi(series, period):
    """Wilder-style RSI over the last `period` deltas; None if too short."""
    if len(series) < period + 1:
        return None
    deltas = [series[i] - series[i - 1] for i in range(1, len(series))]
    recent = deltas[-period:]
    gains = [d for d in recent if d > 0]
    losses = [-d for d in recent if d < 0]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def window_high(series, window):
    """Highest value in the last `window` points."""
    return max(series[-window:])
```

- [ ] **Step 4: Run, verify pass**

Run: `python -m pytest tests/test_indicators.py -v`
Expected: PASS (8 passed).

- [ ] **Step 5: Commit**

```bash
git add bot/strategies/indicators.py tests/test_indicators.py
git commit -m "feat: add technical indicators module"
```

---

### Task 3: margin_flip strategy

**Files:**
- Create: `bot/strategies/margin_flip.py`
- Test: `tests/test_margin_flip.py`

Active flipping. No history needed. `margin = high - tax - low`. Tax = `min(floor(high*0.02), 5_000_000)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_margin_flip.py
from types import SimpleNamespace
from bot.strategies.base import MarketData
from bot.strategies.margin_flip import MarginFlip


def md(item_id, low, high, vol, limit=1000):
    return MarketData(item_id=item_id, name=f"i{item_id}", low=low, high=high,
                      vol_1h=vol, history=[], buy_limit=limit)


def test_finds_profitable_item():
    s = MarginFlip(min_margin=10, min_vol=100, min_roi=0.0)
    buys = s.find_buys([md(1, low=100, high=130, vol=500)], budget=10_000)
    assert len(buys) == 1
    assert buys[0].item_id == 1
    assert buys[0].qty > 0


def test_filters_low_volume():
    s = MarginFlip(min_margin=10, min_vol=1000, min_roi=0.0)
    assert s.find_buys([md(1, 100, 130, vol=10)], budget=10_000) == []


def test_filters_thin_margin():
    s = MarginFlip(min_margin=100, min_vol=100, min_roi=0.0)
    # margin = 130 - 2 - 100 = 28 < 100
    assert s.find_buys([md(1, 100, 130, vol=500)], budget=10_000) == []


def test_should_sell_at_target():
    s = MarginFlip(target_pct=0.05, stop_loss_pct=0.10)
    pos = SimpleNamespace(buy_price=100)
    m = md(1, low=104, high=106, vol=500)   # high 106 >= 100*1.05=105
    assert s.should_sell(pos, m).sell is True


def test_should_sell_on_stop_loss():
    s = MarginFlip(target_pct=0.05, stop_loss_pct=0.10)
    pos = SimpleNamespace(buy_price=100)
    m = md(1, low=85, high=89, vol=500)      # high 89 <= 100*0.90=90
    assert s.should_sell(pos, m).sell is True


def test_should_hold_in_between():
    s = MarginFlip(target_pct=0.05, stop_loss_pct=0.10)
    pos = SimpleNamespace(buy_price=100)
    m = md(1, low=98, high=100, vol=500)
    assert s.should_sell(pos, m).sell is False
```

- [ ] **Step 2: Run, verify failure**

Run: `python -m pytest tests/test_margin_flip.py -v`
Expected: FAIL — no module `bot.strategies.margin_flip`.

- [ ] **Step 3: Implement margin_flip**

```python
# bot/strategies/margin_flip.py
"""Active flipping: buy items with a healthy spread after GE tax."""

from math import floor

from bot.strategies.base import Strategy, BuySignal, SellDecision
from bot.strategies.sizing import size_qty

TAX_RATE = 0.02
TAX_CAP = 5_000_000


def ge_tax(price):
    return min(floor(price * TAX_RATE), TAX_CAP)


class MarginFlip(Strategy):
    name = "margin_flip"
    description = "Active flip: buy low, sell at target margin after tax."

    def __init__(self, **params):
        self.params = {**self.default_params(), **params}

    def default_params(self):
        return {"min_margin": 50, "min_vol": 100, "min_roi": 0.0,
                "target_pct": 0.03, "stop_loss_pct": 0.05}

    def find_buys(self, markets, budget):
        p = self.params
        out = []
        remaining = budget
        for m in markets:
            if not m.low or not m.high:
                continue
            margin = m.high - ge_tax(m.high) - m.low
            roi = margin / m.low if m.low else 0
            if (margin < p["min_margin"] or m.vol_1h < p["min_vol"]
                    or roi < p["min_roi"]):
                continue
            qty = size_qty(m.low, remaining, m.buy_limit)
            if qty <= 0:
                continue
            out.append(BuySignal(item_id=m.item_id, price=m.low, qty=qty,
                                 reason=f"margin {margin} roi {roi:.1%}"))
            remaining -= m.low * qty
        return out

    def should_sell(self, position, market):
        p = self.params
        target = position.buy_price * (1 + p["target_pct"])
        stop = position.buy_price * (1 - p["stop_loss_pct"])
        if market.high >= target:
            return SellDecision(sell=True, reason="target reached")
        if market.high <= stop:
            return SellDecision(sell=True, reason="stop-loss")
        return SellDecision(sell=False, reason="hold")
```

- [ ] **Step 4: Run, verify pass**

Run: `python -m pytest tests/test_margin_flip.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add bot/strategies/margin_flip.py tests/test_margin_flip.py
git commit -m "feat: add margin_flip strategy"
```

---

### Task 4: mean_reversion strategy

**Files:**
- Create: `bot/strategies/mean_reversion.py`
- Test: `tests/test_mean_reversion.py`

Buy when current price is below `mean - k*stdev` of history. Sell when price returns to the mean, or stop-loss.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_mean_reversion.py
from types import SimpleNamespace
from bot.strategies.base import MarketData
from bot.strategies.mean_reversion import MeanReversion


def candles(prices):
    return [{"avgHighPrice": p, "avgLowPrice": p} for p in prices]


def md(low, high, hist, vol=1000, limit=1000):
    return MarketData(item_id=1, name="i", low=low, high=high, vol_1h=vol,
                      history=candles(hist), buy_limit=limit)


def test_buys_when_below_band():
    s = MeanReversion(lookback=5, k=1.0, min_vol=100)
    # history mean ~100, stdev>0; current low well below band
    m = md(low=80, high=82, hist=[100, 110, 90, 105, 95])
    buys = s.find_buys([m], budget=10_000)
    assert len(buys) == 1


def test_no_buy_when_within_band():
    s = MeanReversion(lookback=5, k=1.0, min_vol=100)
    m = md(low=100, high=102, hist=[100, 110, 90, 105, 95])
    assert s.find_buys([m], budget=10_000) == []


def test_sell_at_mean():
    s = MeanReversion(lookback=5, k=1.0, min_vol=100, stop_loss_pct=0.2)
    pos = SimpleNamespace(buy_price=80)
    m = md(low=99, high=101, hist=[100, 110, 90, 105, 95])  # mean 100, high>=mean
    assert s.should_sell(pos, m).sell is True


def test_sell_on_stop_loss():
    s = MeanReversion(lookback=5, k=1.0, min_vol=100, stop_loss_pct=0.1)
    pos = SimpleNamespace(buy_price=80)
    m = md(low=70, high=71, hist=[100, 110, 90, 105, 95])   # high 71 <= 72
    assert s.should_sell(pos, m).sell is True
```

- [ ] **Step 2: Run, verify failure**

Run: `python -m pytest tests/test_mean_reversion.py -v`
Expected: FAIL — no module `bot.strategies.mean_reversion`.

- [ ] **Step 3: Implement mean_reversion**

```python
# bot/strategies/mean_reversion.py
"""Investing: buy statistically cheap items, sell back to the mean."""

from bot.strategies.base import Strategy, BuySignal, SellDecision
from bot.strategies.sizing import size_qty
from bot.strategies import indicators as ind


class MeanReversion(Strategy):
    name = "mean_reversion"
    description = "Buy below mean - k*stdev, sell back to mean."

    def __init__(self, **params):
        self.params = {**self.default_params(), **params}

    def default_params(self):
        return {"lookback": 30, "k": 2.0, "min_vol": 50, "stop_loss_pct": 0.15}

    def _band_low(self, market):
        series = ind.price_series(market.history)
        p = self.params
        if len(series) < p["lookback"]:
            return None, None
        window = series[-p["lookback"]:]
        mu = ind.mean(window)
        sd = ind.stdev(window)
        return mu - p["k"] * sd, mu

    def find_buys(self, markets, budget):
        out = []
        remaining = budget
        for m in markets:
            if m.vol_1h < self.params["min_vol"] or not m.low:
                continue
            band_low, _ = self._band_low(m)
            if band_low is None or m.low >= band_low:
                continue
            qty = size_qty(m.low, remaining, m.buy_limit)
            if qty <= 0:
                continue
            out.append(BuySignal(item_id=m.item_id, price=m.low, qty=qty,
                                 reason=f"below band {band_low:.0f}"))
            remaining -= m.low * qty
        return out

    def should_sell(self, position, market):
        stop = position.buy_price * (1 - self.params["stop_loss_pct"])
        if market.high <= stop:
            return SellDecision(sell=True, reason="stop-loss")
        _, mu = self._band_low(market)
        if mu is not None and market.high >= mu:
            return SellDecision(sell=True, reason="reverted to mean")
        return SellDecision(sell=False, reason="hold")
```

- [ ] **Step 4: Run, verify pass**

Run: `python -m pytest tests/test_mean_reversion.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add bot/strategies/mean_reversion.py tests/test_mean_reversion.py
git commit -m "feat: add mean_reversion strategy"
```

---

### Task 5: bollinger strategy

**Files:**
- Create: `bot/strategies/bollinger.py`
- Test: `tests/test_bollinger.py`

Buy when price at/below the lower Bollinger band; sell at/above the middle band, or stop-loss.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bollinger.py
from types import SimpleNamespace
from bot.strategies.base import MarketData
from bot.strategies.bollinger import Bollinger


def candles(prices):
    return [{"avgHighPrice": p, "avgLowPrice": p} for p in prices]


def md(low, high, hist):
    return MarketData(item_id=1, name="i", low=low, high=high, vol_1h=1000,
                      history=candles(hist), buy_limit=1000)


HIST = [10, 12, 14, 12, 10, 12, 14, 12, 10, 12]  # mid 11.8


def test_buys_at_lower_band():
    s = Bollinger(period=10, k=2.0, min_vol=100)
    assert len(s.find_buys([md(low=8, high=9, hist=HIST)], budget=10_000)) == 1


def test_no_buy_above_lower_band():
    s = Bollinger(period=10, k=2.0, min_vol=100)
    assert s.find_buys([md(low=12, high=13, hist=HIST)], budget=10_000) == []


def test_sell_at_mid_band():
    s = Bollinger(period=10, k=2.0, min_vol=100, stop_loss_pct=0.5)
    pos = SimpleNamespace(buy_price=8)
    assert s.should_sell(pos, md(low=12, high=13, hist=HIST)).sell is True
```

- [ ] **Step 2: Run, verify failure**

Run: `python -m pytest tests/test_bollinger.py -v`
Expected: FAIL — no module `bot.strategies.bollinger`.

- [ ] **Step 3: Implement bollinger**

```python
# bot/strategies/bollinger.py
"""Investing: buy at lower Bollinger band, sell at middle band."""

from bot.strategies.base import Strategy, BuySignal, SellDecision
from bot.strategies.sizing import size_qty
from bot.strategies import indicators as ind


class Bollinger(Strategy):
    name = "bollinger"
    description = "Buy at lower band, sell at middle band."

    def __init__(self, **params):
        self.params = {**self.default_params(), **params}

    def default_params(self):
        return {"period": 20, "k": 2.0, "min_vol": 50, "stop_loss_pct": 0.15}

    def _bands(self, market):
        series = ind.price_series(market.history)
        return ind.bollinger(series, self.params["period"], self.params["k"])

    def find_buys(self, markets, budget):
        out = []
        remaining = budget
        for m in markets:
            if m.vol_1h < self.params["min_vol"] or not m.low:
                continue
            bands = self._bands(m)
            if bands is None or m.low > bands[0]:
                continue
            qty = size_qty(m.low, remaining, m.buy_limit)
            if qty <= 0:
                continue
            out.append(BuySignal(item_id=m.item_id, price=m.low, qty=qty,
                                 reason=f"lower band {bands[0]:.0f}"))
            remaining -= m.low * qty
        return out

    def should_sell(self, position, market):
        stop = position.buy_price * (1 - self.params["stop_loss_pct"])
        if market.high <= stop:
            return SellDecision(sell=True, reason="stop-loss")
        bands = self._bands(market)
        if bands is not None and market.high >= bands[1]:
            return SellDecision(sell=True, reason="reached middle band")
        return SellDecision(sell=False, reason="hold")
```

- [ ] **Step 4: Run, verify pass**

Run: `python -m pytest tests/test_bollinger.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add bot/strategies/bollinger.py tests/test_bollinger.py
git commit -m "feat: add bollinger strategy"
```

---

### Task 6: rsi strategy

**Files:**
- Create: `bot/strategies/rsi.py`
- Test: `tests/test_rsi.py`

Buy when RSI < `lo` (oversold); sell when RSI > `hi` (overbought), or stop-loss.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_rsi.py
from types import SimpleNamespace
from bot.strategies.base import MarketData
from bot.strategies.rsi import Rsi


def candles(prices):
    return [{"avgHighPrice": p, "avgLowPrice": p} for p in prices]


def md(low, high, hist):
    return MarketData(item_id=1, name="i", low=low, high=high, vol_1h=1000,
                      history=candles(hist), buy_limit=1000)


FALLING = list(range(30, 14, -1))   # strictly falling -> RSI 0 (oversold)
RISING = list(range(14, 30))        # strictly rising -> RSI 100 (overbought)


def test_buys_when_oversold():
    s = Rsi(rsi_period=14, lo=30, hi=70, min_vol=100)
    assert len(s.find_buys([md(low=10, high=11, hist=FALLING)], budget=10_000)) == 1


def test_no_buy_when_not_oversold():
    s = Rsi(rsi_period=14, lo=30, hi=70, min_vol=100)
    assert s.find_buys([md(low=10, high=11, hist=RISING)], budget=10_000) == []


def test_sell_when_overbought():
    s = Rsi(rsi_period=14, lo=30, hi=70, min_vol=100, stop_loss_pct=0.9)
    pos = SimpleNamespace(buy_price=10)
    assert s.should_sell(pos, md(low=28, high=29, hist=RISING)).sell is True
```

- [ ] **Step 2: Run, verify failure**

Run: `python -m pytest tests/test_rsi.py -v`
Expected: FAIL — no module `bot.strategies.rsi`.

- [ ] **Step 3: Implement rsi**

```python
# bot/strategies/rsi.py
"""Investing: buy oversold (RSI<lo), sell overbought (RSI>hi)."""

from bot.strategies.base import Strategy, BuySignal, SellDecision
from bot.strategies.sizing import size_qty
from bot.strategies import indicators as ind


class Rsi(Strategy):
    name = "rsi"
    description = "Buy when RSI oversold, sell when overbought."

    def __init__(self, **params):
        self.params = {**self.default_params(), **params}

    def default_params(self):
        return {"rsi_period": 14, "lo": 30, "hi": 70, "min_vol": 50,
                "stop_loss_pct": 0.15}

    def _rsi(self, market):
        series = ind.price_series(market.history)
        return ind.rsi(series, self.params["rsi_period"])

    def find_buys(self, markets, budget):
        out = []
        remaining = budget
        for m in markets:
            if m.vol_1h < self.params["min_vol"] or not m.low:
                continue
            r = self._rsi(m)
            if r is None or r >= self.params["lo"]:
                continue
            qty = size_qty(m.low, remaining, m.buy_limit)
            if qty <= 0:
                continue
            out.append(BuySignal(item_id=m.item_id, price=m.low, qty=qty,
                                 reason=f"rsi {r:.0f}"))
            remaining -= m.low * qty
        return out

    def should_sell(self, position, market):
        stop = position.buy_price * (1 - self.params["stop_loss_pct"])
        if market.high <= stop:
            return SellDecision(sell=True, reason="stop-loss")
        r = self._rsi(market)
        if r is not None and r > self.params["hi"]:
            return SellDecision(sell=True, reason=f"rsi {r:.0f} overbought")
        return SellDecision(sell=False, reason="hold")
```

- [ ] **Step 4: Run, verify pass**

Run: `python -m pytest tests/test_rsi.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add bot/strategies/rsi.py tests/test_rsi.py
git commit -m "feat: add rsi strategy"
```

---

### Task 7: crash_recovery strategy

**Files:**
- Create: `bot/strategies/crash_recovery.py`
- Test: `tests/test_crash_recovery.py`

Buy when current price has dropped at least `drop_pct` below the historical floor's reference (max of the floor lookback window) but is still above a stable floor (min of window). Sell back toward the pre-crash reference, or stop-loss.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_crash_recovery.py
from types import SimpleNamespace
from bot.strategies.base import MarketData
from bot.strategies.crash_recovery import CrashRecovery


def candles(prices):
    return [{"avgHighPrice": p, "avgLowPrice": p} for p in prices]


def md(low, high, hist):
    return MarketData(item_id=1, name="i", low=low, high=high, vol_1h=1000,
                      history=candles(hist), buy_limit=1000)


# reference high ~100, stable floor ~95; current 80 = 20% below ref
STABLE = [100, 98, 96, 100, 97, 95, 99, 96, 100, 98]


def test_buys_after_crash():
    s = CrashRecovery(drop_pct=0.15, floor_lookback=10, min_vol=100)
    assert len(s.find_buys([md(low=80, high=81, hist=STABLE)], budget=10_000)) == 1


def test_no_buy_without_crash():
    s = CrashRecovery(drop_pct=0.15, floor_lookback=10, min_vol=100)
    assert s.find_buys([md(low=99, high=100, hist=STABLE)], budget=10_000) == []


def test_sell_on_recovery():
    s = CrashRecovery(drop_pct=0.15, floor_lookback=10, min_vol=100,
                      stop_loss_pct=0.5, recover_pct=0.9)
    pos = SimpleNamespace(buy_price=80)
    # reference ~100; recover target 0.9*100=90; high 92 >= 90
    assert s.should_sell(pos, md(low=91, high=92, hist=STABLE)).sell is True
```

- [ ] **Step 2: Run, verify failure**

Run: `python -m pytest tests/test_crash_recovery.py -v`
Expected: FAIL — no module `bot.strategies.crash_recovery`.

- [ ] **Step 3: Implement crash_recovery**

```python
# bot/strategies/crash_recovery.py
"""Investing: buy overreaction crashes with a stable floor, sell on recovery."""

from bot.strategies.base import Strategy, BuySignal, SellDecision
from bot.strategies.sizing import size_qty
from bot.strategies import indicators as ind


class CrashRecovery(Strategy):
    name = "crash_recovery"
    description = "Buy after a crash above a stable floor, sell on recovery."

    def __init__(self, **params):
        self.params = {**self.default_params(), **params}

    def default_params(self):
        return {"drop_pct": 0.20, "floor_lookback": 30, "min_vol": 50,
                "stop_loss_pct": 0.15, "recover_pct": 0.9}

    def _reference(self, market):
        series = ind.price_series(market.history)
        p = self.params
        if len(series) < p["floor_lookback"]:
            return None
        window = series[-p["floor_lookback"]:]
        return max(window)

    def find_buys(self, markets, budget):
        out = []
        remaining = budget
        for m in markets:
            if m.vol_1h < self.params["min_vol"] or not m.low:
                continue
            ref = self._reference(m)
            if ref is None:
                continue
            crash_line = ref * (1 - self.params["drop_pct"])
            if m.low > crash_line:
                continue
            qty = size_qty(m.low, remaining, m.buy_limit)
            if qty <= 0:
                continue
            out.append(BuySignal(item_id=m.item_id, price=m.low, qty=qty,
                                 reason=f"crashed below {crash_line:.0f}"))
            remaining -= m.low * qty
        return out

    def should_sell(self, position, market):
        stop = position.buy_price * (1 - self.params["stop_loss_pct"])
        if market.high <= stop:
            return SellDecision(sell=True, reason="stop-loss")
        ref = self._reference(market)
        if ref is not None and market.high >= ref * self.params["recover_pct"]:
            return SellDecision(sell=True, reason="recovered")
        return SellDecision(sell=False, reason="hold")
```

- [ ] **Step 4: Run, verify pass**

Run: `python -m pytest tests/test_crash_recovery.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add bot/strategies/crash_recovery.py tests/test_crash_recovery.py
git commit -m "feat: add crash_recovery strategy"
```

---

### Task 8: ma_crossover strategy

**Files:**
- Create: `bot/strategies/ma_crossover.py`
- Test: `tests/test_ma_crossover.py`

Buy on golden cross (fast SMA above slow SMA); sell on death cross (fast below slow), or stop-loss.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ma_crossover.py
from types import SimpleNamespace
from bot.strategies.base import MarketData
from bot.strategies.ma_crossover import MaCrossover


def candles(prices):
    return [{"avgHighPrice": p, "avgLowPrice": p} for p in prices]


def md(low, high, hist):
    return MarketData(item_id=1, name="i", low=low, high=high, vol_1h=1000,
                      history=candles(hist), buy_limit=1000)


UPTREND = [10, 10, 10, 10, 10, 11, 12, 13, 14, 15]    # fast(3) > slow(8)
DOWNTREND = [15, 14, 13, 12, 11, 10, 9, 8, 7, 6]       # fast(3) < slow(8)


def test_buys_on_golden_cross():
    s = MaCrossover(fast_ma=3, slow_ma=8, min_vol=100)
    assert len(s.find_buys([md(low=15, high=16, hist=UPTREND)], budget=10_000)) == 1


def test_no_buy_on_downtrend():
    s = MaCrossover(fast_ma=3, slow_ma=8, min_vol=100)
    assert s.find_buys([md(low=6, high=7, hist=DOWNTREND)], budget=10_000) == []


def test_sell_on_death_cross():
    s = MaCrossover(fast_ma=3, slow_ma=8, min_vol=100, stop_loss_pct=0.9)
    pos = SimpleNamespace(buy_price=6)
    assert s.should_sell(pos, md(low=6, high=7, hist=DOWNTREND)).sell is True
```

- [ ] **Step 2: Run, verify failure**

Run: `python -m pytest tests/test_ma_crossover.py -v`
Expected: FAIL — no module `bot.strategies.ma_crossover`.

- [ ] **Step 3: Implement ma_crossover**

```python
# bot/strategies/ma_crossover.py
"""Trend: buy on golden cross (fast SMA over slow), sell on death cross."""

from bot.strategies.base import Strategy, BuySignal, SellDecision
from bot.strategies.sizing import size_qty
from bot.strategies import indicators as ind


class MaCrossover(Strategy):
    name = "ma_crossover"
    description = "Buy fast-over-slow SMA cross, sell on the reverse."

    def __init__(self, **params):
        self.params = {**self.default_params(), **params}

    def default_params(self):
        return {"fast_ma": 10, "slow_ma": 30, "min_vol": 50, "stop_loss_pct": 0.15}

    def _cross(self, market):
        """Return (fast, slow) SMA or (None, None) if too short."""
        series = ind.price_series(market.history)
        fast = ind.sma(series, self.params["fast_ma"])
        slow = ind.sma(series, self.params["slow_ma"])
        return fast, slow

    def find_buys(self, markets, budget):
        out = []
        remaining = budget
        for m in markets:
            if m.vol_1h < self.params["min_vol"] or not m.low:
                continue
            fast, slow = self._cross(m)
            if fast is None or slow is None or fast <= slow:
                continue
            qty = size_qty(m.low, remaining, m.buy_limit)
            if qty <= 0:
                continue
            out.append(BuySignal(item_id=m.item_id, price=m.low, qty=qty,
                                 reason="golden cross"))
            remaining -= m.low * qty
        return out

    def should_sell(self, position, market):
        stop = position.buy_price * (1 - self.params["stop_loss_pct"])
        if market.high <= stop:
            return SellDecision(sell=True, reason="stop-loss")
        fast, slow = self._cross(market)
        if fast is not None and slow is not None and fast < slow:
            return SellDecision(sell=True, reason="death cross")
        return SellDecision(sell=False, reason="hold")
```

- [ ] **Step 4: Run, verify pass**

Run: `python -m pytest tests/test_ma_crossover.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add bot/strategies/ma_crossover.py tests/test_ma_crossover.py
git commit -m "feat: add ma_crossover strategy"
```

---

### Task 9: momentum strategy

**Files:**
- Create: `bot/strategies/momentum.py`
- Test: `tests/test_momentum.py`

Buy when the last `lookback` mid-prices are strictly rising. Sell when the most recent step is not rising (trend flattened/reversed), or stop-loss.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_momentum.py
from types import SimpleNamespace
from bot.strategies.base import MarketData
from bot.strategies.momentum import Momentum


def candles(prices):
    return [{"avgHighPrice": p, "avgLowPrice": p} for p in prices]


def md(low, high, hist):
    return MarketData(item_id=1, name="i", low=low, high=high, vol_1h=1000,
                      history=candles(hist), buy_limit=1000)


RISING = [10, 11, 12, 13, 14]
FLAT = [10, 11, 12, 13, 13]


def test_buys_on_rising_run():
    s = Momentum(lookback=4, min_vol=100)
    assert len(s.find_buys([md(low=14, high=15, hist=RISING)], budget=10_000)) == 1


def test_no_buy_when_not_rising():
    s = Momentum(lookback=4, min_vol=100)
    assert s.find_buys([md(low=13, high=14, hist=FLAT)], budget=10_000) == []


def test_sell_when_trend_flattens():
    s = Momentum(lookback=4, min_vol=100, stop_loss_pct=0.9)
    pos = SimpleNamespace(buy_price=10)
    assert s.should_sell(pos, md(low=13, high=14, hist=FLAT)).sell is True
```

- [ ] **Step 2: Run, verify failure**

Run: `python -m pytest tests/test_momentum.py -v`
Expected: FAIL — no module `bot.strategies.momentum`.

- [ ] **Step 3: Implement momentum**

```python
# bot/strategies/momentum.py
"""Trend: buy a sustained rising run, sell when it flattens or reverses."""

from bot.strategies.base import Strategy, BuySignal, SellDecision
from bot.strategies.sizing import size_qty
from bot.strategies import indicators as ind


def _is_rising(series, lookback):
    """True if the last `lookback`+1 points are strictly increasing."""
    if len(series) < lookback + 1:
        return False
    window = series[-(lookback + 1):]
    return all(window[i] < window[i + 1] for i in range(len(window) - 1))


class Momentum(Strategy):
    name = "momentum"
    description = "Buy a rising run, sell when momentum fades."

    def __init__(self, **params):
        self.params = {**self.default_params(), **params}

    def default_params(self):
        return {"lookback": 5, "min_vol": 50, "stop_loss_pct": 0.15}

    def find_buys(self, markets, budget):
        out = []
        remaining = budget
        for m in markets:
            if m.vol_1h < self.params["min_vol"] or not m.low:
                continue
            series = ind.price_series(m.history)
            if not _is_rising(series, self.params["lookback"]):
                continue
            qty = size_qty(m.low, remaining, m.buy_limit)
            if qty <= 0:
                continue
            out.append(BuySignal(item_id=m.item_id, price=m.low, qty=qty,
                                 reason="rising momentum"))
            remaining -= m.low * qty
        return out

    def should_sell(self, position, market):
        stop = position.buy_price * (1 - self.params["stop_loss_pct"])
        if market.high <= stop:
            return SellDecision(sell=True, reason="stop-loss")
        series = ind.price_series(market.history)
        if not _is_rising(series, self.params["lookback"]):
            return SellDecision(sell=True, reason="momentum faded")
        return SellDecision(sell=False, reason="hold")
```

- [ ] **Step 4: Run, verify pass**

Run: `python -m pytest tests/test_momentum.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add bot/strategies/momentum.py tests/test_momentum.py
git commit -m "feat: add momentum strategy"
```

---

### Task 10: breakout strategy

**Files:**
- Create: `bot/strategies/breakout.py`
- Test: `tests/test_breakout.py`

Buy when current price breaks above the highest mid-price of the prior `channel_days` window AND `vol_1h` exceeds `vol_mult` times the average historical volume. Sell on a trailing stop below the position's high-water mark; `should_sell` here uses `position.high_water` if present, else `buy_price`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_breakout.py
from types import SimpleNamespace
from bot.strategies.base import MarketData
from bot.strategies.breakout import Breakout


def candles(prices, vol=100):
    return [{"avgHighPrice": p, "avgLowPrice": p,
             "highPriceVolume": vol, "lowPriceVolume": vol} for p in prices]


def md(low, high, hist, vol_1h):
    return MarketData(item_id=1, name="i", low=low, high=high, vol_1h=vol_1h,
                      history=hist, buy_limit=1000)


CHANNEL = candles([10, 11, 10, 12, 11, 10, 12, 11], vol=100)  # prior high 12


def test_buys_on_breakout_with_volume():
    s = Breakout(channel_days=8, vol_mult=2.0, min_vol=100)
    # current high 15 > prior high 12; vol_1h 500 > 2*200(=high+low vol per candle)
    m = md(low=14, high=15, hist=CHANNEL, vol_1h=500)
    assert len(s.find_buys([m], budget=10_000)) == 1


def test_no_buy_without_breakout():
    s = Breakout(channel_days=8, vol_mult=2.0, min_vol=100)
    m = md(low=11, high=12, hist=CHANNEL, vol_1h=500)   # 12 not above prior high 12
    assert s.find_buys([m], budget=10_000) == []


def test_no_buy_without_volume_spike():
    s = Breakout(channel_days=8, vol_mult=2.0, min_vol=100)
    m = md(low=14, high=15, hist=CHANNEL, vol_1h=150)   # below 2*avg vol
    assert s.find_buys([m], budget=10_000) == []


def test_trailing_stop_sells():
    s = Breakout(channel_days=8, vol_mult=2.0, min_vol=100, trail_pct=0.1)
    pos = SimpleNamespace(buy_price=14, high_water=20)
    # trailing stop = 20*0.9 = 18; high 17 <= 18 -> sell
    assert s.should_sell(pos, md(low=16, high=17, hist=CHANNEL, vol_1h=100)).sell is True


def test_trailing_stop_holds():
    s = Breakout(channel_days=8, vol_mult=2.0, min_vol=100, trail_pct=0.1)
    pos = SimpleNamespace(buy_price=14, high_water=20)
    assert s.should_sell(pos, md(low=18, high=19, hist=CHANNEL, vol_1h=100)).sell is False
```

- [ ] **Step 2: Run, verify failure**

Run: `python -m pytest tests/test_breakout.py -v`
Expected: FAIL — no module `bot.strategies.breakout`.

- [ ] **Step 3: Implement breakout**

```python
# bot/strategies/breakout.py
"""Trend: buy breakouts above a price channel on a volume spike; trailing stop."""

from bot.strategies.base import Strategy, BuySignal, SellDecision
from bot.strategies.sizing import size_qty
from bot.strategies import indicators as ind


class Breakout(Strategy):
    name = "breakout"
    description = "Buy channel breakout + volume spike, exit on trailing stop."

    def __init__(self, **params):
        self.params = {**self.default_params(), **params}

    def default_params(self):
        return {"channel_days": 30, "vol_mult": 2.0, "min_vol": 50,
                "trail_pct": 0.10}

    def _avg_candle_volume(self, history, window):
        vols = [(c.get("highPriceVolume") or 0) + (c.get("lowPriceVolume") or 0)
                for c in history[-window:]]
        return sum(vols) / len(vols) if vols else 0

    def find_buys(self, markets, budget):
        p = self.params
        out = []
        remaining = budget
        for m in markets:
            if m.vol_1h < p["min_vol"] or not m.low or not m.high:
                continue
            series = ind.price_series(m.history)
            if len(series) < p["channel_days"]:
                continue
            prior_high = max(series[-p["channel_days"]:])
            if m.high <= prior_high:
                continue
            avg_vol = self._avg_candle_volume(m.history, p["channel_days"])
            if m.vol_1h < p["vol_mult"] * avg_vol:
                continue
            qty = size_qty(m.low, remaining, m.buy_limit)
            if qty <= 0:
                continue
            out.append(BuySignal(item_id=m.item_id, price=m.low, qty=qty,
                                 reason=f"breakout above {prior_high:.0f}"))
            remaining -= m.low * qty
        return out

    def should_sell(self, position, market):
        peak = getattr(position, "high_water", None) or position.buy_price
        trailing_stop = peak * (1 - self.params["trail_pct"])
        if market.high <= trailing_stop:
            return SellDecision(sell=True, reason="trailing stop")
        return SellDecision(sell=False, reason="hold")
```

- [ ] **Step 4: Run, verify pass**

Run: `python -m pytest tests/test_breakout.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest`
Expected: PASS — all Phase 1 + Phase 2 tests green.

- [ ] **Step 6: Commit**

```bash
git add bot/strategies/breakout.py tests/test_breakout.py
git commit -m "feat: add breakout strategy"
```

---

### Task 11: Loader integration check

**Files:**
- Test: `tests/test_strategies_discovered.py`

Verify the real `bot/strategies/` directory yields all eight strategies via the Phase 1 loader — proves auto-discovery works on the actual files.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_strategies_discovered.py
import os
from bot.strategies.loader import load_strategies

STRAT_DIR = os.path.join(os.path.dirname(__file__), "..", "bot", "strategies")


def test_all_eight_strategies_discovered():
    found = load_strategies(os.path.abspath(STRAT_DIR))
    assert set(found) == {
        "margin_flip", "mean_reversion", "bollinger", "rsi",
        "crash_recovery", "ma_crossover", "momentum", "breakout",
    }


def test_each_has_default_params():
    found = load_strategies(os.path.abspath(STRAT_DIR))
    for name, strat in found.items():
        assert isinstance(strat.default_params(), dict)
```

- [ ] **Step 2: Run, verify it passes**

Run: `python -m pytest tests/test_strategies_discovered.py -v`
Expected: PASS (2 passed). Note: `indicators.py` and `sizing.py` define no `Strategy` subclass, so the loader correctly ignores them.

- [ ] **Step 3: Run the full suite**

Run: `python -m pytest`
Expected: PASS — everything green.

- [ ] **Step 4: Commit**

```bash
git add tests/test_strategies_discovered.py
git commit -m "test: verify all strategies auto-discovered"
```

---

## Self-Review Notes

- **Spec coverage:** all 8 strategies from [[Strategy System]] implemented (margin_flip + mean_reversion + bollinger + rsi + crash_recovery + ma_crossover + momentum + breakout), each with buy logic, exit signal, and stop-loss. Indicators + sizing shared. Loader integration verified (Task 11). Max-hold deliberately deferred to the engine (Phase 4) — noted in the plan header.
- **Type consistency:** every strategy uses `__init__(self, **params)`, `find_buys(self, markets, budget)`, `should_sell(self, position, market)`, matching the Phase 1 `Strategy` contract. `MarketData` extended once (Task 1) and used consistently. `BuySignal(item_id, price, qty, reason)` and `SellDecision(sell, reason)` constructed identically everywhere.
- **Placeholder scan:** every code step has complete code; every run step has expected output. No TODOs.
- **Note for Phase 4:** `breakout.should_sell` reads optional `position.high_water`; the position manager must maintain a high-water mark for breakout positions. Documented here so it isn't missed.

## Next Phase
After Phase 2 is green: write the Phase 3 plan ([[Backtesting]]) — run these strategies over `/timeseries` history and rank them.
