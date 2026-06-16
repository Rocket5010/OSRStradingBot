from bot.strategies.loader import load_strategies

STRAT_SRC = '''
from bot.strategies.base import Strategy, SellDecision

class MyStrat(Strategy):
    name = "mystrat"
    description = "demo"
    def find_buys(self, market, budget): return []
    def should_sell(self, position, market): return SellDecision(sell=False, reason="")
    def default_params(self): return {}
'''


def test_loads_strategy_from_dir(tmp_path):
    (tmp_path / "mystrat.py").write_text(STRAT_SRC)
    found = load_strategies(str(tmp_path))
    assert "mystrat" in found
    assert found["mystrat"].description == "demo"


def test_ignores_non_strategy_files(tmp_path):
    (tmp_path / "notes.py").write_text("x = 1\n")
    found = load_strategies(str(tmp_path))
    assert found == {}


def test_skips_broken_strategy_file(tmp_path):
    (tmp_path / "broken.py").write_text("import nonexistent_module_xyz\n")
    (tmp_path / "mystrat.py").write_text(STRAT_SRC)
    found = load_strategies(str(tmp_path))
    assert "mystrat" in found      # good one still loads
    assert "broken" not in found
