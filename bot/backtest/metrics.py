# bot/backtest/metrics.py
"""Performance metrics for a backtest run."""


def total_profit(trades):
    return sum(t["pl"] for t in trades)


def hit_rate(trades):
    if not trades:
        return 0.0
    wins = sum(1 for t in trades if t["pl"] > 0)
    return wins / len(trades)


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
