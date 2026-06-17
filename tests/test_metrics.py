from bot.backtest.metrics import total_profit, hit_rate, max_drawdown


def test_total_profit():
    assert total_profit([{"pl": 10}, {"pl": -5}, {"pl": 3}]) == 8


def test_total_profit_empty():
    assert total_profit([]) == 0


def test_hit_rate():
    assert hit_rate([{"pl": 10}, {"pl": -5}, {"pl": 3}]) == 2 / 3


def test_hit_rate_no_trades():
    assert hit_rate([]) == 0.0


def test_max_drawdown():
    # peak 120 then trough 90 -> (120-90)/120 = 0.25
    assert max_drawdown([100, 120, 90, 110]) == 0.25


def test_max_drawdown_monotonic_up():
    assert max_drawdown([100, 110, 120]) == 0.0


def test_max_drawdown_empty():
    assert max_drawdown([]) == 0.0
