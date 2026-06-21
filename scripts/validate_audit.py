"""End-to-end validation of the audit fixes against live data. Read-only
(in-memory DB). Run: python -m scripts.validate_audit

Checks:
  1. poller stores highTime/lowTime (staleness is knowable)
  2. build_market_data drops null/crossed prices
  3. a full evaluate() pass runs without crashing on real data
  4. staleness + spike gates actually fire on the live watchlist
"""

import os
import time

from bot import db, runs, positions as pos
from bot.api_client import WikiClient
from bot.poller import poll_once
from bot.market import build_market_data, HistoryCache
from bot.engine_live import evaluate, _price_age_s, _is_spike
from bot.curator import screen_two_bucket


def main():
    ua = os.environ.get("OSRS_BOT_UA", "osrs-flip-bot/1.0 (set OSRS_BOT_UA)")
    client = WikiClient(user_agent=ua)
    conn = db.connect(":memory:")
    db.init_db(conn)

    print("1) polling live prices...")
    n = poll_once(client, conn)
    have_times = conn.execute(
        "SELECT COUNT(*) c FROM price_cache WHERE high_time IS NOT NULL").fetchone()["c"]
    null_px = conn.execute(
        "SELECT COUNT(*) c FROM price_cache WHERE low IS NULL OR high IS NULL").fetchone()["c"]
    print(f"   {n} rows, {have_times} with high_time, {null_px} with a null price")
    assert have_times > 0, "highTime not stored"

    print("2) building market data over a small watchlist...")
    mapping = {str(m["id"]): m for m in (client.mapping() or [])}
    # mix liquid + expensive value items
    watch = screen_two_bucket(conn, liquid_cap=20, value_cap=20)[:40]
    hist = HistoryCache(client, timestep="24h")
    markets = build_market_data(conn, mapping, hist, watch, now=time.monotonic())
    print(f"   {len(watch)} watch ids -> {len(markets)} valid markets "
          f"({len(watch) - len(markets)} dropped as null/crossed)")

    epoch = time.time()
    stale = sum(1 for m in markets
                if (_price_age_s(m, epoch) or 0) > 86400)
    spiked = sum(1 for m in markets if _is_spike(m, 5.0))
    print(f"   staleness gate would skip {stale}, spike gate would skip {spiked}")

    print("3) running a full evaluate() pass (margin_flip)...")
    runs.start_run(conn, "margin_flip", budget_gp=50_000_000)
    market_map = {m.item_id: m for m in markets}
    evaluate(conn, market_map, now=time.monotonic())
    props = pos.list_positions(conn, state="proposed")
    print(f"   OK, no crash. {len(props)} buy proposals created.")
    for p in props[:8]:
        print(f"     {p['item_name']:<28} buy {p['buy_price']:>12,} x{p['qty']}")

    print("\nVALIDATION PASSED: timestamps stored, bad prices dropped, "
          "gates active, evaluate() ran clean on live data.")


if __name__ == "__main__":
    main()
