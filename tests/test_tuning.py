from bot import tuning
from bot.backtest.engine import BacktestResult
from bot.strategies.base import BuySignal, SellDecision


def test_combos_cartesian_product():
    combos = list(tuning._combos({"a": [1, 2], "b": [3]}))
    assert combos == [{"a": 1, "b": 3}, {"a": 2, "b": 3}]


def test_folds_splits_into_segments():
    candles = list(range(120))
    fs = tuning.folds(candles, n_folds=4, min_len=25)
    assert len(fs) == 4
    assert fs[0][0] == 0 and fs[-1][-1] == 119      # cover the whole series
    assert sum(len(f) for f in fs) == 120           # disjoint, no overlap/gap


def test_folds_too_short_returns_single_or_empty():
    assert tuning.folds(list(range(10)), 4, min_len=25) == []
    assert len(tuning.folds(list(range(30)), 4, min_len=25)) == 1


def test_conservative_score_zero_without_trades():
    r = BacktestResult(total_profit=0, n_trades=0, hit_rate=0.0,
                       max_drawdown=0.0, final_equity=0)
    assert tuning.conservative_score(r) == 0.0


def test_conservative_score_weights_hit_rate_and_drawdown():
    r = BacktestResult(total_profit=0, n_trades=4, hit_rate=0.5,
                       max_drawdown=0.5, final_equity=0,
                       profit_per_day=100.0)
    # 100 * 0.5 / (1 + 2*0.5) = 50 / 2 = 25
    assert tuning.conservative_score(r) == 25.0


class ThreshStub:
    """Buys while low <= thresh; sells as soon as it's in profit. A high thresh
    trades and profits here; a low thresh never buys (zero score)."""
    name = "threshstub"

    def __init__(self, **p):
        self.p = {"thresh": 100, **p}

    def find_buys(self, markets, budget):
        m = markets[0]
        if m.low <= self.p["thresh"] and budget >= m.low:
            return [BuySignal(item_id=m.item_id, price=m.low, qty=1, reason="")]
        return []

    def should_sell(self, position, market):
        return SellDecision(sell=market.high > position.buy_price, reason="")


def _candles(n=120):
    v = {"highPriceVolume": 1000, "lowPriceVolume": 1000}
    return [{"avgHighPrice": 110, "avgLowPrice": 100, **v} for _ in range(n)]


def test_tune_strategy_picks_profitable_combo(monkeypatch):
    monkeypatch.setattr(tuning, "GRIDS", {"threshstub": {"thresh": [50, 150]}})
    params, score = tuning.tune_strategy(
        "threshstub", ThreshStub, {1: _candles(), 2: _candles()}, budget=1000)
    assert params == {"thresh": 150}     # only this one trades+profits
    assert score > 0


def test_tune_strategy_no_grid_returns_base():
    params, score = tuning.tune_strategy(
        "unknown", ThreshStub, {1: _candles()}, budget=1000,
        base_params={"x": 1})
    assert params == {"x": 1} and score == 0.0
