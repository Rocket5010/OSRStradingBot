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
        conn.execute(
            "INSERT INTO price_cache(item_id, low, high, vol_1h, ts) "
            "VALUES(?, ?, ?, ?, ?) "
            "ON CONFLICT(item_id) DO UPDATE SET "
            "low=excluded.low, high=excluded.high, vol_1h=excluded.vol_1h, ts=excluded.ts",
            (int(item_id), lt.get("low"), lt.get("high"), vol_1h, ts),
        )
        written += 1
    conn.commit()
    return written
