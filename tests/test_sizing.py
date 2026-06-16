from bot.strategies.sizing import size_qty


def test_limited_by_budget():
    # budget 1000, price 100, no buy limit -> 10
    assert size_qty(price=100, budget=1000, buy_limit=0) == 10


def test_limited_by_buy_limit():
    # budget huge, price 100, buy_limit 4 -> 4
    assert size_qty(price=100, budget=10**9, buy_limit=4) == 4


def test_zero_when_cannot_afford_one():
    assert size_qty(price=100, budget=50, buy_limit=0) == 0


def test_zero_price_returns_zero():
    assert size_qty(price=0, budget=1000, buy_limit=10) == 0
