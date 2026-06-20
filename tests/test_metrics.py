from bot.backtest.metrics import (
    total_profit, hit_rate, max_drawdown, profit_per_day, risk_score)


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


def test_profit_per_day():
    # 300 profit over 30 daily candles -> 10/day
    assert profit_per_day([{"pl": 300}], n_candles=30) == 10.0


def test_profit_per_day_min_one_day():
    # never divide by zero
    assert profit_per_day([{"pl": 50}], n_candles=0) == 50.0


def test_risk_score_penalizes_drawdown():
    trades = [{"pl": 300}]
    # 10/day, dd 0.5 -> 10/1.5
    assert risk_score(trades, n_candles=30, drawdown=0.5) == 10.0 / 1.5


def test_risk_score_no_trades_is_zero():
    assert risk_score([], n_candles=30, drawdown=0.0) == 0.0


def test_risk_score_prefers_faster_steady_earner():
    # slow: 5000 over 300 days, no drawdown; fast: 4000 over 30 days, no drawdown.
    # raw profit favours slow, but risk_score (gp/day) must favour fast.
    slow = risk_score([{"pl": 5000}], n_candles=300, drawdown=0.0)
    fast = risk_score([{"pl": 4000}], n_candles=30, drawdown=0.0)
    assert fast > slow
