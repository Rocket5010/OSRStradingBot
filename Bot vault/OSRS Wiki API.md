# OSRS Wiki API

The free data source. Fetched by `api_client.py` ([[Modules]]). See [[Constraints|free-only]].

Base: `https://prices.runescape.wiki/api/v1/osrs`

| Endpoint | Gives |
|---|---|
| `/latest` | live high/low per item |
| `/5m`, `/1h` | time-averaged price + **volume** |
| `/timeseries?timestep=24h&id=ID` | historical candles (~365 pts/call) |
| `/mapping` | item meta: buy limit, members flag, value |

## Rules
- Requires a `User-Agent` header with contact info.
- ~1 req/sec politeness. No monthly quota.
- `/5m` recomputed every 5 min → see [[Constraints|poll cadence]].

## Used by
- [[Strategy System]] — live signals
- [[Backtesting]] — `/timeseries` history
- [[Bond Goal]] — live bond price (item id 13190)
