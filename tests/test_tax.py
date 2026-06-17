from bot.tax import ge_tax


def test_two_percent_floored():
    assert ge_tax(1000) == 20
    assert ge_tax(149) == 2          # floor(2.98)


def test_capped_at_5m():
    assert ge_tax(10**9) == 5_000_000


def test_zero():
    assert ge_tax(0) == 0
