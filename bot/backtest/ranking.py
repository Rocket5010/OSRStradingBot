# bot/backtest/ranking.py
"""Run multiple strategies over the same candles and rank by profit."""

from bot.backtest.engine import run_backtest


def rank_strategies(factories, candles, budget, **kwargs):
    """factories: {name: zero-arg callable -> Strategy}. Returns list of
    (name, BacktestResult) sorted by total_profit descending."""
    results = []
    for name, factory in factories.items():
        result = run_backtest(factory(), candles, budget, **kwargs)
        results.append((name, result))
    results.sort(key=lambda pair: pair[1].total_profit, reverse=True)
    return results
