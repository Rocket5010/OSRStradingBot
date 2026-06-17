# tests/test_market.py
from bot import db
from bot.market import position_view, HistoryCache, build_market_data


def test_position_view_exposes_attributes():
    conn = db.connect(":memory:")
    db.init_db(conn)
    conn.execute("INSERT INTO positions(item_id,item_name,strategy,state,buy_price,"
                 "qty,high_water,ref_price) VALUES(2,'Cb','rsi','filled',100,10,150,130)")
    conn.commit()
    row = conn.execute("SELECT * FROM positions WHERE id=1").fetchone()
    v = position_view(row)
    assert v.buy_price == 100 and v.high_water == 150 and v.ref_price == 130


class StubClient:
    def __init__(self): self.calls = 0
    def timeseries(self, item_id, timestep):
        self.calls += 1
        return [{"avgHighPrice": 100, "avgLowPrice": 90}]


def test_history_cache_refetches_only_when_stale():
    client = StubClient()
    cache = HistoryCache(client, timestep="24h", max_age_s=300)
    t = [1000.0]
    cache.get(2, now=t[0])
    cache.get(2, now=t[0] + 100)   # within max_age -> cached
    assert client.calls == 1
    cache.get(2, now=t[0] + 400)   # stale -> refetch
    assert client.calls == 2


def test_build_market_data_joins_sources():
    conn = db.connect(":memory:")
    db.init_db(conn)
    conn.execute("INSERT INTO price_cache(item_id,low,high,vol_1h,ts) "
                 "VALUES(2,150,200,5000,'t')")
    conn.commit()
    mapping = {"2": {"name": "Cannonball", "limit": 11000, "members": False}}
    cache = HistoryCache(StubClient(), timestep="24h", max_age_s=300)
    markets = build_market_data(conn, mapping, cache, [2], now=0.0)
    assert len(markets) == 1
    m = markets[0]
    assert m.item_id == 2 and m.name == "Cannonball"
    assert m.low == 150 and m.high == 200 and m.vol_1h == 5000
    assert m.buy_limit == 11000 and m.members is False
    assert m.history == [{"avgHighPrice": 100, "avgLowPrice": 90}]


def test_build_skips_items_without_price_cache():
    conn = db.connect(":memory:")
    db.init_db(conn)
    mapping = {"2": {"name": "X", "limit": 0, "members": False}}
    cache = HistoryCache(StubClient(), timestep="24h", max_age_s=300)
    assert build_market_data(conn, mapping, cache, [2], now=0.0) == []
