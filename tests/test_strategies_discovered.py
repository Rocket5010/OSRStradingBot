import os
from bot.strategies.loader import load_strategies

STRAT_DIR = os.path.join(os.path.dirname(__file__), "..", "bot", "strategies")


def test_all_eight_strategies_discovered():
    found = load_strategies(os.path.abspath(STRAT_DIR))
    assert set(found) == {
        "margin_flip", "mean_reversion", "bollinger", "rsi",
        "crash_recovery", "ma_crossover", "momentum", "breakout",
    }


def test_each_has_default_params():
    found = load_strategies(os.path.abspath(STRAT_DIR))
    for name, strat in found.items():
        assert isinstance(strat.default_params(), dict)
