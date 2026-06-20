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
        return {"channel_days": 30, "vol_mult": 2.0, "min_vol": 10,
                "trail_pct": 0.10, "vol_fraction": 0.25}

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
            qty = size_qty(m.low, remaining, m.buy_limit, m.vol_1h,
                           p["vol_fraction"])
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
