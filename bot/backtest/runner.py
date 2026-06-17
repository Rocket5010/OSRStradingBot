# bot/backtest/runner.py
"""Fetch historical candles via the Wiki client and rank strategies."""

from bot.backtest.ranking import rank_strategies


def run_ranking(client, item_id, factories, budget, timestep="24h", **kwargs):
    """Fetch /timeseries for one item and rank the given strategy factories."""
    candles = client.timeseries(item_id, timestep)
    return rank_strategies(factories, candles, budget, item_id=item_id, **kwargs)


def format_ranking(ranked):
    """Return a printable table string from rank_strategies output."""
    lines = [f"{'Strategy':<16}{'Profit':>12}{'Trades':>8}{'Hit%':>7}{'MaxDD%':>8}"]
    lines.append("-" * len(lines[0]))
    for name, r in ranked:
        lines.append(f"{name:<16}{r.total_profit:>12,}{r.n_trades:>8}"
                     f"{r.hit_rate * 100:>6.0f}%{r.max_drawdown * 100:>7.1f}%")
    return "\n".join(lines)
