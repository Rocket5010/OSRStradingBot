"""Quantity sizing for buy signals: bounded by budget and GE buy limit."""


def size_qty(price, budget, buy_limit, volume=None, vol_fraction=1.0):
    """Max units affordable within budget, capped by buy_limit (0 = no cap) and
    by a fraction of recent traded volume (None = no volume cap). vol_fraction
    keeps a buy to a slice of the market's flow (e.g. 0.25 = at most 25% of the
    hourly volume) so the order can actually fill without moving the price —
    important for thin, expensive items where the full volume cap is too loose."""
    if price <= 0:
        return 0
    qty = budget // price
    if buy_limit and buy_limit > 0:
        qty = min(qty, buy_limit)
    if volume and volume > 0:
        qty = min(qty, int(volume * vol_fraction))
    return int(qty)
