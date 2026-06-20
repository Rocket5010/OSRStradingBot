from bot import db, backtest_rank
from bot.strategies.base import BuySignal, SellDecision


class StubClient:
    def timeseries(self, item_id, timestep):
        # item 2 doubles (profitable); others flat. Volume present (real candles
        # always have it; the engine caps qty by it).
        v = {"highPriceVolume": 1000, "lowPriceVolume": 1000}
        if item_id == 2:
            return [{"avgHighPrice": 100, "avgLowPrice": 100, **v},
                    {"avgHighPrice": 200, "avgLowPrice": 190, **v}]
        return [{"avgHighPrice": 100, "avgLowPrice": 100, **v},
                {"avgHighPrice": 100, "avgLowPrice": 100, **v}]


class Always:
    name = "always"
    def __init__(self, **p): self.bought = False
    def find_buys(self, markets, budget):
        m = markets[0]
        if self.bought or budget < m.low: return []
        self.bought = True
        return [BuySignal(item_id=m.item_id, price=m.low, qty=1, reason="")]
    def should_sell(self, position, market):
        return SellDecision(sell=market.high >= 150, reason="")


def loader_stub(_dir):
    return {"always": Always()}


def test_rank_aggregates_and_orders(monkeypatch):
    monkeypatch.setattr(backtest_rank, "load_strategies", loader_stub)
    ranking = backtest_rank.rank_over_items(StubClient(), [1, 2, 3], budget=1000,
                                            min_candles=2, on_progress=None)
    assert ranking[0]["strategy"] == "always"
    assert ranking[0]["profit"] > 0       # item 2 profit aggregated in
    assert ranking[0]["trades"] >= 1
    assert 0 <= ranking[0]["win_rate"] <= 1


def test_rank_reports_progress(monkeypatch):
    monkeypatch.setattr(backtest_rank, "load_strategies", loader_stub)
    seen = []
    backtest_rank.rank_over_items(StubClient(), [1, 2, 3], budget=1000,
                                  min_candles=2, on_progress=lambda d, t: seen.append((d, t)))
    assert seen[-1] == (3, 3)


def test_buy_limits_parses_mapping():
    class C:
        def mapping(self):
            return [{"id": 4151, "limit": 70}, {"id": 2, "limit": 13000},
                    {"id": 99, "limit": None}, {"bad": "row"}]
    out = backtest_rank.buy_limits(C())
    assert out[4151] == 70 and out[2] == 13000 and out[99] == 0
    assert "bad" not in out


def test_buy_limits_tolerates_missing_method():
    assert backtest_rank.buy_limits(StubClient()) == {}   # no mapping() -> {}


def test_save_and_get_ranking():
    conn = db.connect(":memory:")
    db.init_db(conn)
    assert backtest_rank.get_ranking(conn)["ranking"] == []   # default empty
    backtest_rank.save_ranking(conn, [{"strategy": "x", "profit": 5,
                                       "trades": 1, "win_rate": 1.0}], n_items=3)
    g = backtest_rank.get_ranking(conn)
    assert g["ranking"][0]["strategy"] == "x" and g["n_items"] == 3
    assert g["finished"] is not None
