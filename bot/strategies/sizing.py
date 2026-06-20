"""Quantity sizing for buy signals: bounded by budget and GE buy limit."""


def size_qty(price, budget, buy_limit, volume=None):
    """Max units affordable within budget, capped by buy_limit (0 = no cap) and
    by recent traded volume (None = no cap — you can't buy more than trades)."""
    if price <= 0:
        return 0
    qty = budget // price
    if buy_limit and buy_limit > 0:
        qty = min(qty, buy_limit)
    if volume and volume > 0:
        qty = min(qty, volume)
    return int(qty)
