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
