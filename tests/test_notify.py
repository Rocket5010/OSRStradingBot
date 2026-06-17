from bot import notify


def test_notify_no_url_is_noop():
    calls = []
    assert notify.notify("", "hi", poster=lambda u, p: calls.append((u, p))) is False
    assert calls == []


def test_notify_posts_content():
    calls = []
    ok = notify.notify("http://hook", "hello", poster=lambda u, p: calls.append((u, p)))
    assert ok is True
    assert calls == [("http://hook", {"content": "hello"})]


def test_format_buy():
    msg = notify.format_buy("Abyssal whip", 1500000, 5, "below band")
    assert "Abyssal whip" in msg and "BUY" in msg.upper()


def test_format_sell():
    msg = notify.format_sell("Abyssal whip", 1700000, "reverted to mean")
    assert "Abyssal whip" in msg and "SELL" in msg.upper()
