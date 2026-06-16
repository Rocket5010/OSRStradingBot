# tests/test_margin_flip.py
from types import SimpleNamespace
from bot.strategies.base import MarketData
from bot.strategies.margin_flip import MarginFlip


def md(item_id, low, high, vol, limit=1000):
    return MarketData(item_id=item_id, name=f"i{item_id}", low=low, high=high,
                      vol_1h=vol, history=[], buy_limit=limit)


def test_finds_profitable_item():
    s = MarginFlip(min_margin=10, min_vol=100, min_roi=0.0)
    buys = s.find_buys([md(1, low=100, high=130, vol=500)], budget=10_000)
    assert len(buys) == 1
    assert buys[0].item_id == 1
    assert buys[0].qty > 0


def test_filters_low_volume():
    s = MarginFlip(min_margin=10, min_vol=1000, min_roi=0.0)
    assert s.find_buys([md(1, 100, 130, vol=10)], budget=10_000) == []


def test_filters_thin_margin():
    s = MarginFlip(min_margin=100, min_vol=100, min_roi=0.0)
    # margin = 130 - 2 - 100 = 28 < 100
    assert s.find_buys([md(1, 100, 130, vol=500)], budget=10_000) == []


def test_should_sell_at_target():
    s = MarginFlip(target_pct=0.05, stop_loss_pct=0.10)
    pos = SimpleNamespace(buy_price=100)
    m = md(1, low=104, high=106, vol=500)   # high 106 >= 100*1.05=105
    assert s.should_sell(pos, m).sell is True


def test_should_sell_on_stop_loss():
    s = MarginFlip(target_pct=0.05, stop_loss_pct=0.10)
    pos = SimpleNamespace(buy_price=100)
    m = md(1, low=85, high=89, vol=500)      # high 89 <= 100*0.90=90
    assert s.should_sell(pos, m).sell is True


def test_should_hold_in_between():
    s = MarginFlip(target_pct=0.05, stop_loss_pct=0.10)
    pos = SimpleNamespace(buy_price=100)
    m = md(1, low=98, high=100, vol=500)
    assert s.should_sell(pos, m).sell is False


def test_budget_depletes_across_items():
    s = MarginFlip(min_margin=10, min_vol=100, min_roi=0.0)
    # two profitable items, price 100 each, buy_limit large; budget only 150
    markets = [md(1, low=100, high=130, vol=500, limit=10_000),
               md(2, low=100, high=130, vol=500, limit=10_000)]
    buys = s.find_buys(markets, budget=150)
    spent = sum(b.price * b.qty for b in buys)
    assert spent <= 150
