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
        return {"fast_ma": 10, "slow_ma": 30, "min_vol": 10, "stop_loss_pct": 0.15}

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
            qty = size_qty(m.low, remaining, m.buy_limit, m.vol_1h)
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
