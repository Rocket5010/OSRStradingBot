# bot/tax.py
"""GE sell tax: 2% of sell price, floored, capped at 5M per item."""

from math import floor

TAX_RATE = 0.02
TAX_CAP = 5_000_000


def ge_tax(price):
    return min(floor(price * TAX_RATE), TAX_CAP)
