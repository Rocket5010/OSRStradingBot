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
            qty = size_qty(m.low, remaining, m.buy_limit, m.vol_1h)
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
