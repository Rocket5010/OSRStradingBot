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
