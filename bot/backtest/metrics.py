# bot/backtest/metrics.py
"""Performance metrics for a backtest run."""


def total_profit(trades):
    return sum(t["pl"] for t in trades)


def hit_rate(trades):
    if not trades:
        return 0.0
    wins = sum(1 for t in trades if t["pl"] > 0)
    return wins / len(trades)


def profit_per_day(trades, n_candles, candle_days=1):
    """Average profit earned per day of the backtest window. Time-normalizes
    profit so a strategy that earns slowly over a long window doesn't outrank a
    faster one. n_candles at a 24h timestep == days."""
    days = max(n_candles, 1) * candle_days
    return total_profit(trades) / days


def risk_score(trades, n_candles, drawdown, candle_days=1):
    """Risk- and time-adjusted ranking score: profit/day penalized by drawdown.
    Used to rank strategies and curation picks toward the bond goal (gp/day)
    without rewarding volatile strategies that just got lucky on raw profit."""
    if not trades:
        return 0.0
    return profit_per_day(trades, n_candles, candle_days) / (1.0 + drawdown)


def max_drawdown(equity_curve):
    """Largest peak-to-trough drop as a fraction of the peak."""
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    worst = 0.0
    for v in equity_curve:
        if v > peak:
            peak = v
        if peak > 0:
            drop = (peak - v) / peak
            if drop > worst:
                worst = drop
    return worst
