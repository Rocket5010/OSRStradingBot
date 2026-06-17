from bot import db, goal


class StubClient:
    def latest_item(self, item_id):
        assert item_id == 13190
        return {"high": 14000000, "low": 13300000}


def fresh():
    conn = db.connect(":memory:")
    db.init_db(conn)
    return conn


def test_refresh_sets_bond_price_and_defaults():
    conn = fresh()
    goal.refresh_bond_goal(conn, StubClient(), now_iso="2026-06-17T00:00:00+00:00")
    assert db.get_config(conn, "bond_price") == "14000000"
    assert db.get_config(conn, "bond_days") == "14"
    assert db.get_config(conn, "goal_period_start") == "2026-06-17T00:00:00+00:00"


def test_refresh_keeps_existing_period_start():
    conn = fresh()
    db.set_config(conn, "goal_period_start", "2026-06-01T00:00:00+00:00")
    goal.refresh_bond_goal(conn, StubClient(), now_iso="2026-06-17T00:00:00+00:00")
    assert db.get_config(conn, "goal_period_start") == "2026-06-01T00:00:00+00:00"
