"""One poll cycle: fetch latest + 1h volume, write to price_cache."""

from datetime import datetime, timezone


def poll_once(client, conn):
    latest = client.latest()
    one_hour = {str(k): v for k, v in client.one_hour().items()}
    ts = datetime.now(timezone.utc).isoformat()
    written = 0
    for item_id, lt in latest.items():
        vol = one_hour.get(item_id, {})
        vol_1h = (vol.get("highPriceVolume") or 0) + (vol.get("lowPriceVolume") or 0)
        # highTime/lowTime are unix epoch seconds of the last insta-buy/insta-sell.
        # Stored so downstream can tell a fresh price from a days-old frozen one.
        conn.execute(
            "INSERT INTO price_cache(item_id, low, high, vol_1h, ts, high_time, low_time) "
            "VALUES(?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(item_id) DO UPDATE SET "
            "low=excluded.low, high=excluded.high, vol_1h=excluded.vol_1h, "
            "ts=excluded.ts, high_time=excluded.high_time, low_time=excluded.low_time",
            (int(item_id), lt.get("low"), lt.get("high"), vol_1h, ts,
             lt.get("highTime"), lt.get("lowTime")),
        )
        written += 1
    conn.commit()
    return written
