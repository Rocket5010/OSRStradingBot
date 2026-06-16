"""Quantity sizing for buy signals: bounded by budget and GE buy limit."""


def size_qty(price, budget, buy_limit):
    """Max units affordable within budget, capped by buy_limit (0 = no cap)."""
    if price <= 0:
        return 0
    qty = budget // price
    if buy_limit and buy_limit > 0:
        qty = min(qty, buy_limit)
    return int(qty)
