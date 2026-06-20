"""One-shot sanity check: poll live prices, run the two-bucket screen, and show
what each bucket selected (with names/price/volume/limit). Confirms expensive
low-volume items actually surface in the value bucket. Read-only — uses an
in-memory DB, writes nothing to the real bot DB.

Run: python -m scripts.verify_two_bucket
"""

import os

from bot import db, curator
from bot.api_client import WikiClient
from bot.poller import poll_once
from bot.backtest_rank import buy_limits


def main():
    ua = os.environ.get("OSRS_BOT_UA", "osrs-flip-bot/1.0 (set OSRS_BOT_UA)")
    client = WikiClient(user_agent=ua)
    conn = db.connect(":memory:")
    db.init_db(conn)

    print("Polling live prices...")
    n = poll_once(client, conn)
    print(f"  price_cache rows: {n}")

    mapping = {str(r["id"]): r for r in (client.mapping() or [])}
    limits = buy_limits(client)

    liquid = curator.screen_candidates(conn, min_vol=100, cap=150)
    full = curator.screen_two_bucket(conn)
    value_only = [i for i in full if i not in set(liquid)]

    def show(title, ids, n=15):
        print(f"\n{title} ({len(ids)} items, showing {min(n, len(ids))}):")
        print(f"  {'id':>7} {'name':<28} {'low':>12} {'high':>12} "
              f"{'vol_1h':>8} {'limit':>7}")
        for item_id in ids[:n]:
            row = conn.execute("SELECT low, high, vol_1h FROM price_cache "
                               "WHERE item_id=?", (item_id,)).fetchone()
            name = mapping.get(str(item_id), {}).get("name", str(item_id))
            print(f"  {item_id:>7} {name[:28]:<28} {row['low']:>12,} "
                  f"{row['high']:>12,} {row['vol_1h']:>8,} "
                  f"{limits.get(item_id, 0):>7,}")

    show("LIQUID bucket (top volume)", liquid)
    show("VALUE-ONLY (expensive, surfaced by the value bucket)", value_only)

    if value_only:
        print(f"\nOK: {len(value_only)} expensive items entered via the value "
              f"bucket that the old volume-only screen would have missed.")
    else:
        print("\nNo value-only items — check value_min_price / floors.")


if __name__ == "__main__":
    main()
