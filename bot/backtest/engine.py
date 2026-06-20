# bot/backtest/engine.py
"""Walk-forward backtest of a strategy over historical candles."""

from dataclasses import dataclass, field

from bot.strategies.base import MarketData
from bot.tax import ge_tax
from bot.backtest.metrics import (
    total_profit, hit_rate, max_drawdown, profit_per_day, risk_score)


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
    n_candles: int = 0
    roi: float = 0.0
    profit_per_day: float = 0.0
    risk_score: float = 0.0


def _close(pos, sell_price):
    proceeds = (sell_price - ge_tax(sell_price)) * pos.qty
    cost = pos.buy_price * pos.qty
    return {"pl": proceeds - cost, "buy_price": pos.buy_price,
            "sell_price": sell_price, "qty": pos.qty}


def run_backtest(strategy, candles, budget, item_id=1, name="item",
                 buy_limit=0, members=False, max_hold_steps=None,
                 candle_hours=24):
    cash = budget
    open_positions = []
    trades = []
    equity_curve = []
    last_high = None
    # GE buy limits reset every 4h. One candle spans candle_hours, so within it
    # you can refill the limit candle_hours/4 times. per_candle_limit models the
    # realistic max units accumulable in one candle; None = no limit known.
    windows = max(1, candle_hours // 4)
    per_candle_limit = buy_limit * windows if buy_limit and buy_limit > 0 else None

    for i, c in enumerate(candles):
        hi, lo = c.get("avgHighPrice"), c.get("avgLowPrice")
        if hi is None or lo is None:
            equity_curve.append(cash + sum(
                (last_high - ge_tax(last_high)) * p.qty for p in open_positions
            ) if last_high else cash)
            continue
        last_high = hi
        vol = (c.get("highPriceVolume") or 0) + (c.get("lowPriceVolume") or 0)
        # history includes the current candle: at step i the current candle's
        # prices are known (same data find_buys/should_sell act on). Not look-ahead
        # — future candles (i+1..) are never exposed.
        # buy_limit=0 in the MarketData: the strategy sizes by budget/volume only,
        # and the engine applies the realistic per-candle fill cap below (a single
        # 4h limit would be far too strict for a multi-window candle).
        md = MarketData(item_id=item_id, name=name, low=lo, high=hi, vol_1h=vol,
                        history=candles[:i + 1], buy_limit=0, members=members)

        # sells first
        for pos in list(open_positions):
            pos.high_water = max(pos.high_water, hi)
            # max_hold_steps = N: close once the position has been held N steps
            # since its open candle (open at index k closes at index k+N).
            forced = max_hold_steps is not None and (i - pos.open_index) >= max_hold_steps
            decision = strategy.should_sell(pos, md)
            if decision.sell or forced:
                trades.append(_close(pos, hi))
                cash += (hi - ge_tax(hi)) * pos.qty
                open_positions.remove(pos)

        # buys — size from a FIXED budget (not growing cash) so profitable
        # round-trips don't compound into exponential nonsense, and never buy
        # more than the period's traded volume (you can't buy what didn't trade).
        for sig in strategy.find_buys([md], budget):
            qty = min(sig.qty, vol)
            if per_candle_limit is not None:
                qty = min(qty, per_candle_limit)
            if qty <= 0:
                continue
            cost = sig.price * qty
            if cost > cash:
                continue
            cash -= cost
            open_positions.append(Position(item_id=item_id, buy_price=sig.price,
                                           qty=qty, high_water=hi, open_index=i))

        equity_curve.append(cash + sum(
            (hi - ge_tax(hi)) * p.qty for p in open_positions))

    # liquidate any remaining positions at the last valid high
    if last_high is not None:
        for pos in list(open_positions):
            trades.append(_close(pos, last_high))
            cash += (last_high - ge_tax(last_high)) * pos.qty
            open_positions.remove(pos)

    dd = max_drawdown(equity_curve)
    n_candles = len(candles)
    tp = total_profit(trades)
    return BacktestResult(
        total_profit=tp,
        n_trades=len(trades),
        hit_rate=hit_rate(trades),
        max_drawdown=dd,
        final_equity=cash,
        trades=trades,
        n_candles=n_candles,
        roi=(tp / budget) if budget else 0.0,
        profit_per_day=profit_per_day(trades, n_candles),
        risk_score=risk_score(trades, n_candles, dd),
    )
