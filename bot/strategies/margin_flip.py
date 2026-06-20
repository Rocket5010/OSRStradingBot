# bot/strategies/margin_flip.py
"""Active flipping: buy items with a healthy spread after GE tax."""

from bot.strategies.base import Strategy, BuySignal, SellDecision
from bot.strategies.sizing import size_qty
from bot.tax import ge_tax


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
            qty = size_qty(m.low, remaining, m.buy_limit, m.vol_1h)
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
