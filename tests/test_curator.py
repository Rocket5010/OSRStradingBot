# tests/test_curator.py
from bot import db, curator
from bot.strategies.base import BuySignal, SellDecision


def fresh():
    conn = db.connect(":memory:")
    db.init_db(conn)
    return conn


def add_price(conn, item_id, low, high, vol):
    conn.execute("INSERT INTO price_cache(item_id,low,high,vol_1h,ts) "
                 "VALUES(?,?,?,?,'t')", (item_id, low, high, vol))
    conn.commit()


def test_screen_filters_by_volume_and_price():
    conn = fresh()
    add_price(conn, 1, low=100, high=110, vol=5000)
    add_price(conn, 2, low=100, high=110, vol=10)      # too thin
    add_price(conn, 3, low=10**9, high=10**9, vol=9000)  # too pricey
    ids = curator.screen_candidates(conn, min_vol=100, max_price=1_000_000, cap=50)
    assert ids == [1]


def test_screen_caps_and_sorts_by_volume():
    conn = fresh()
    add_price(conn, 1, 100, 110, vol=100)
    add_price(conn, 2, 100, 110, vol=9000)
    add_price(conn, 3, 100, 110, vol=5000)
    ids = curator.screen_candidates(conn, min_vol=1, max_price=None, cap=2)
    assert ids == [2, 3]   # top 2 by volume


class WinOnItem2:
    """Profitable only for item 2; flat elsewhere."""
    name = "winner"
    def __init__(self, **p): self.bought = False
    def find_buys(self, markets, budget):
        m = markets[0]
        if self.bought or budget < m.low or m.item_id != 2:
            return []
        self.bought = True
        return [BuySignal(item_id=m.item_id, price=m.low, qty=1, reason="")]
    def should_sell(self, position, market):
        return SellDecision(sell=market.high >= 200, reason="")


class StubClient:
    def timeseries(self, item_id, timestep):
        # item 2 doubles; others flat
        if item_id == 2:
            return [{"avgHighPrice": 100, "avgLowPrice": 100},
                    {"avgHighPrice": 200, "avgLowPrice": 190}]
        return [{"avgHighPrice": 100, "avgLowPrice": 100},
                {"avgHighPrice": 100, "avgLowPrice": 100}]


def test_curate_ranks_by_backtest_profit():
    conn = fresh()
    picks = curator.curate(conn, StubClient(), WinOnItem2,
                           candidate_ids=[1, 2, 3], budget=1000, top_n=2,
                           min_candles=2)
    assert picks[0] == 2          # only profitable item ranks first
    assert 2 in picks


def test_save_and_get_watchlist():
    conn = fresh()
    curator.save_watchlist(conn, [4151, 11802])
    assert curator.get_watchlist(conn) == [4151, 11802]
    assert curator.get_watchlist(db.connect(":memory:") or conn) is not None


def test_get_watchlist_default_when_unset():
    conn = fresh()
    assert curator.get_watchlist(conn, default=[1, 2]) == [1, 2]
