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
        return {"drop_pct": 0.20, "floor_lookback": 30, "min_vol": 10,
                "stop_loss_pct": 0.15, "recover_pct": 0.9, "vol_fraction": 0.25}

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
            qty = size_qty(m.low, remaining, m.buy_limit, m.vol_1h,
                           self.params["vol_fraction"])
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
        ref = getattr(position, "ref_price", None) or self._reference(market)
        if ref is not None and market.high >= ref * self.params["recover_pct"]:
            return SellDecision(sell=True, reason="recovered")
        return SellDecision(sell=False, reason="hold")
