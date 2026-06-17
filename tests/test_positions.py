import pytest
from bot import db, runs, positions as pos


def fresh():
    conn = db.connect(":memory:")
    db.init_db(conn)
    return conn


def make(conn, run_id=None, buy_price=100, qty=10):
    return pos.create_proposed(conn, strategy="rsi", item_id=2, item_name="Cb",
                               buy_price=buy_price, qty=qty, run_id=run_id,
                               sell_target=120, stop_loss=90)


def test_create_is_proposed():
    conn = fresh()
    pid = make(conn)
    assert pos.get(conn, pid)["state"] == "proposed"


def test_happy_path_to_sold_computes_pl():
    conn = fresh()
    rid = runs.start_run(conn, "rsi", budget_gp=10_000)
    pid = make(conn, run_id=rid, buy_price=100, qty=10)
    pos.accept(conn, pid)
    assert runs.available(conn, rid) == 10_000 - 1000   # committed
    pos.mark_filled(conn, pid)
    pos.start_selling(conn, pid)
    pl = pos.mark_sold(conn, pid, sell_price=120)
    # proceeds = (120 - floor(120*0.02)=2) * 10 = 1180; cost 1000 -> pl 180
    assert pl == 180
    row = pos.get(conn, pid)
    assert row["state"] == "sold" and row["realized_pl"] == 180
    assert runs.available(conn, rid) == 10_000   # capital released


def test_dismiss_from_proposed():
    conn = fresh()
    pid = make(conn)
    pos.dismiss(conn, pid)
    assert pos.get(conn, pid)["state"] == "dismissed"


def test_cancel_releases_capital():
    conn = fresh()
    rid = runs.start_run(conn, "rsi", budget_gp=10_000)
    pid = make(conn, run_id=rid, buy_price=100, qty=10)
    pos.accept(conn, pid)
    pos.cancel(conn, pid)
    assert pos.get(conn, pid)["state"] == "cancelled"
    assert runs.available(conn, rid) == 10_000


def test_illegal_transition_raises():
    conn = fresh()
    pid = make(conn)
    with pytest.raises(ValueError):
        pos.mark_sold(conn, pid, 120)   # cannot sell a proposed position


def test_list_filters_by_state():
    conn = fresh()
    a = make(conn)
    b = make(conn)
    pos.dismiss(conn, b)
    proposed = pos.list_positions(conn, state="proposed")
    assert {p["id"] for p in proposed} == {a}


def test_cancel_from_selling_releases_capital():
    conn = fresh()
    rid = runs.start_run(conn, "rsi", budget_gp=10_000)
    pid = make(conn, run_id=rid, buy_price=100, qty=10)
    pos.accept(conn, pid)
    pos.mark_filled(conn, pid)
    pos.start_selling(conn, pid)
    pos.cancel(conn, pid)
    assert pos.get(conn, pid)["state"] == "cancelled"
    assert runs.available(conn, rid) == 10_000


def test_cancel_from_filled_releases_capital():
    conn = fresh()
    rid = runs.start_run(conn, "rsi", budget_gp=10_000)
    pid = make(conn, run_id=rid, buy_price=100, qty=10)
    pos.accept(conn, pid)
    pos.mark_filled(conn, pid)
    pos.cancel(conn, pid)
    assert pos.get(conn, pid)["state"] == "cancelled"
    assert runs.available(conn, rid) == 10_000


def test_high_water_and_ref_price_default_and_update():
    conn = fresh()
    pid = pos.create_proposed(conn, strategy="breakout", item_id=2, item_name="Cb",
                              buy_price=100, qty=10, ref_price=130)
    row = pos.get(conn, pid)
    assert row["ref_price"] == 130
    assert row["high_water"] == 100   # defaults to buy_price
    pos.update_high_water(conn, pid, 150)
    assert pos.get(conn, pid)["high_water"] == 150
    pos.update_high_water(conn, pid, 120)   # never decreases
    assert pos.get(conn, pid)["high_water"] == 150
