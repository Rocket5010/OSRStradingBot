from bot import db
from bot.poller import poll_once


class StubClient:
    def latest(self):
        return {"2": {"high": 200, "low": 150}, "4": {"high": 0, "low": 0}}
    def one_hour(self):
        return {"2": {"highPriceVolume": 300, "lowPriceVolume": 200}}


def test_poll_writes_price_cache():
    conn = db.connect(":memory:")
    db.init_db(conn)
    n = poll_once(StubClient(), conn)
    assert n == 2
    row = conn.execute("SELECT * FROM price_cache WHERE item_id=2").fetchone()
    assert row["low"] == 150 and row["high"] == 200 and row["vol_1h"] == 500


def test_poll_zero_volume_when_missing_in_1h():
    conn = db.connect(":memory:")
    db.init_db(conn)
    poll_once(StubClient(), conn)
    row = conn.execute("SELECT * FROM price_cache WHERE item_id=4").fetchone()
    assert row["vol_1h"] == 0


def test_poll_is_upsert():
    conn = db.connect(":memory:")
    db.init_db(conn)
    poll_once(StubClient(), conn)
    poll_once(StubClient(), conn)
    count = conn.execute("SELECT COUNT(*) c FROM price_cache").fetchone()["c"]
    assert count == 2  # not duplicated
