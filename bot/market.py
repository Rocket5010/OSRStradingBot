# bot/market.py
"""Assemble MarketData from price_cache + mapping + cached timeseries, and
adapt position rows into attribute objects for strategies."""

from types import SimpleNamespace

from bot.strategies.base import MarketData


def position_view(row):
    """Wrap a dict-like position row so strategies can use attribute access."""
    return SimpleNamespace(**{k: row[k] for k in row.keys()})


class HistoryCache:
    """Caches /timeseries per item; refetches only when older than max_age_s."""

    def __init__(self, client, timestep="24h", max_age_s=21600):
        self.client = client
        self.timestep = timestep
        self.max_age_s = max_age_s
        self._cache = {}   # item_id -> (fetched_at, candles)

    def get(self, item_id, now):
        entry = self._cache.get(item_id)
        if entry is not None and (now - entry[0]) < self.max_age_s:
            return entry[1]
        candles = self.client.timeseries(item_id, self.timestep)
        self._cache[item_id] = (now, candles)
        return candles


def build_market_data(conn, mapping, history_cache, item_ids, now):
    """One MarketData per item that has a price_cache row. Skips items without
    current prices."""
    markets = []
    for item_id in item_ids:
        row = conn.execute(
            "SELECT * FROM price_cache WHERE item_id=?", (item_id,)).fetchone()
        if row is None:
            continue
        low, high = row["low"], row["high"]
        # Drop unusable rows rather than letting None/garbage reach ge_tax and
        # crash the tick, or letting a crossed book (high < low) fake a margin.
        if low is None or high is None or low <= 0 or high <= 0 or high < low:
            continue
        meta = mapping.get(str(item_id), {})
        markets.append(MarketData(
            item_id=item_id,
            name=meta.get("name", str(item_id)),
            low=low,
            high=high,
            vol_1h=row["vol_1h"],
            history=history_cache.get(item_id, now=now),
            buy_limit=meta.get("limit", 0) or 0,
            members=bool(meta.get("members", False)),
            high_time=row["high_time"] if "high_time" in row.keys() else None,
            low_time=row["low_time"] if "low_time" in row.keys() else None,
        ))
    return markets
