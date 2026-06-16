#!/usr/bin/env python3
"""
OSRS Flip Finder — finner flip-muligheter i Grand Exchange.

Bruker OSRS Wiki Real-time Prices API (gratis, ingen nokkel).
Henter live priser + volum, regner ut margin etter GE-skatt,
og rangerer items etter forventet profitt per syklus.

Botting-regel: dette er KUN en radgiver. Den klikker ikke i spillet.
Du legger inn handler selv i GE.
"""

import json
import time
import urllib.request
import urllib.error
import argparse
from datetime import datetime, timezone

API_BASE = "https://prices.runescape.wiki/api/v1/osrs"
# Wiki ber om User-Agent med kontaktinfo. Endre til din egen.
USER_AGENT = "osrs-flip-finder/1.0 (kontakt: sander.rocket@gmail.com)"

# GE-skatt: 2% pa salg, avrundet ned, tak 5M per item. Bond/visse items fritatt.
GE_TAX_RATE = 0.02
GE_TAX_CAP = 5_000_000


def fetch(endpoint):
    """Hent JSON fra API-endpoint. Returnerer dict."""
    url = f"{API_BASE}/{endpoint}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise SystemExit(f"HTTP-feil {e.code} pa {url}: {e.reason}")
    except urllib.error.URLError as e:
        raise SystemExit(f"Nettverksfeil pa {url}: {e.reason}")


def ge_tax(sell_price):
    """Skatt nar du selger ett item for sell_price."""
    tax = int(sell_price * GE_TAX_RATE)
    return min(tax, GE_TAX_CAP)


def load_data():
    """Hent mapping (meta), 5m og 1h aggregater."""
    mapping = fetch("mapping")          # liste med item-meta
    latest = fetch("latest")["data"]    # live high/low per id
    five_m = fetch("5m")["data"]        # snitt + volum siste 5m
    one_h = fetch("1h")["data"]         # snitt + volum siste 1h
    meta = {str(m["id"]): m for m in mapping}
    return meta, latest, five_m, one_h


def build_rows(meta, latest, five_m, one_h):
    """Slaa sammen kilder til en rad per item med utregnet margin/score."""
    rows = []
    for item_id, lt in latest.items():
        m = meta.get(item_id)
        if not m:
            continue
        buy = lt.get("low")    # det du kan kjope for (instant-buy lav)
        sell = lt.get("high")  # det du kan selge for (instant-sell hoy)
        if not buy or not sell:
            continue

        margin = sell - ge_tax(sell) - buy
        if margin <= 0:
            continue

        limit = m.get("limit") or 0          # GE buy limit per 4t
        # volum fra 1h-aggregat: hvor mange handlet
        vol = one_h.get(item_id, {})
        buy_vol = vol.get("lowPriceVolume") or 0
        sell_vol = vol.get("highPriceVolume") or 0
        traded = buy_vol + sell_vol

        # profitt per syklus = margin * antall du faktisk far kjopt
        # begrenset av buy limit OG av hvor mye som faktisk handles
        cap_qty = limit if limit > 0 else 1000
        profit_cycle = margin * cap_qty
        roi = margin / buy if buy else 0

        rows.append({
            "id": item_id,
            "name": m.get("name", "?"),
            "buy": buy,
            "sell": sell,
            "margin": margin,
            "limit": limit,
            "vol_1h": traded,
            "profit_cycle": profit_cycle,
            "roi": roi,
            "members": m.get("members", False),
        })
    return rows


def fmt(n):
    """Tall til lesbar gp-streng."""
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.0f}K"
    return str(n)


def main():
    ap = argparse.ArgumentParser(description="OSRS Flip Finder")
    ap.add_argument("--min-margin", type=int, default=50,
                    help="Min margin per item (gp). Default 50.")
    ap.add_argument("--min-volume", type=int, default=100,
                    help="Min handlet volum siste time. Default 100.")
    ap.add_argument("--max-buy", type=int, default=0,
                    help="Maks kjopspris per item (gp). 0 = ingen grense.")
    ap.add_argument("--min-roi", type=float, default=0.0,
                    help="Min ROI (f.eks 0.02 = 2%%). Default 0.")
    ap.add_argument("--top", type=int, default=30,
                    help="Antall rader a vise. Default 30.")
    ap.add_argument("--sort", choices=["profit", "roi", "margin", "volume"],
                    default="profit", help="Sorter etter. Default profit.")
    ap.add_argument("--members", choices=["all", "f2p", "p2p"],
                    default="all", help="Filtrer members/f2p.")
    args = ap.parse_args()

    print("Henter data fra OSRS Wiki API ...")
    meta, latest, five_m, one_h = load_data()
    rows = build_rows(meta, latest, five_m, one_h)

    # filtrer
    out = []
    for r in rows:
        if r["margin"] < args.min_margin:
            continue
        if r["vol_1h"] < args.min_volume:
            continue
        if args.max_buy and r["buy"] > args.max_buy:
            continue
        if r["roi"] < args.min_roi:
            continue
        if args.members == "f2p" and r["members"]:
            continue
        if args.members == "p2p" and not r["members"]:
            continue
        out.append(r)

    sort_key = {
        "profit": "profit_cycle",
        "roi": "roi",
        "margin": "margin",
        "volume": "vol_1h",
    }[args.sort]
    out.sort(key=lambda r: r[sort_key], reverse=True)
    out = out[:args.top]

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\nOSRS Flip Finder  -  {ts}")
    print(f"Filter: margin>={args.min_margin} vol>={args.min_volume} "
          f"roi>={args.min_roi} sort={args.sort}\n")

    hdr = f"{'Item':<28}{'Kjop':>10}{'Selg':>10}{'Margin':>9}{'ROI':>7}{'Limit':>8}{'Vol/t':>9}{'Profit/syk':>12}"
    print(hdr)
    print("-" * len(hdr))
    for r in out:
        print(f"{r['name'][:27]:<28}"
              f"{fmt(r['buy']):>10}"
              f"{fmt(r['sell']):>10}"
              f"{fmt(r['margin']):>9}"
              f"{r['roi']*100:>6.1f}%"
              f"{r['limit']:>8}"
              f"{fmt(r['vol_1h']):>9}"
              f"{fmt(r['profit_cycle']):>12}")

    if not out:
        print("Ingen treff. Loosne filtrene.")
    print(f"\n{len(out)} treff. Husk: legg handler selv i GE. Bot klikker ikke.")


if __name__ == "__main__":
    main()
