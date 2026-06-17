# bot/notify.py
"""Optional push notifications via a JSON webhook (Discord-compatible)."""

import json
import urllib.request


def post_json(url, payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status


def notify(webhook_url, message, poster=post_json):
    """Post a message to the webhook. Returns False if no URL configured."""
    if not webhook_url:
        return False
    poster(webhook_url, {"content": message})
    return True


def format_buy(item_name, price, qty, reason):
    return f"🟢 BUY {item_name} — {qty} @ {price:,} gp ({reason})"


def format_sell(item_name, price, reason):
    return f"🟡 SELL {item_name} @ {price:,} gp ({reason})"
