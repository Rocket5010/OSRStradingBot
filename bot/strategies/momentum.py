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
        return {"lookback": 5, "min_vol": 10, "stop_loss_pct": 0.15}

    def find_buys(self, markets, budget):
        out = []
        remaining = budget
        for m in markets:
            if m.vol_1h < self.params["min_vol"] or not m.low:
                continue
            series = ind.price_series(m.history)
            if not _is_rising(series, self.params["lookback"]):
                continue
            qty = size_qty(m.low, remaining, m.buy_limit, m.vol_1h)
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
