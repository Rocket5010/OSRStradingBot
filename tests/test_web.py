# tests/test_web.py
from fastapi.testclient import TestClient
from bot import db
from bot.web import create_app


def client():
    conn = db.connect(":memory:")
    db.init_db(conn)
    return TestClient(create_app(conn))


def test_list_strategies():
    c = client()
    r = c.get("/api/strategies")
    assert r.status_code == 200
    names = {s["name"] for s in r.json()}
    assert "mean_reversion" in names and "margin_flip" in names
    assert all("default_params" in s for s in r.json())


def test_start_and_list_run():
    c = client()
    r = c.post("/api/runs", json={"strategy": "rsi", "budget_gp": 5_000_000,
                                  "params": {"lo": 25}})
    assert r.status_code == 200
    run = r.json()
    assert run["state"] == "running" and run["budget_gp"] == 5_000_000
    listed = c.get("/api/runs").json()
    assert len(listed) == 1


def test_stop_run():
    c = client()
    rid = c.post("/api/runs", json={"strategy": "rsi", "budget_gp": 1}).json()["id"]
    r = c.post(f"/api/runs/{rid}/stop")
    assert r.status_code == 200 and r.json()["state"] == "stopped"


def test_stop_missing_run_404():
    c = client()
    assert c.post("/api/runs/999/stop").status_code == 404


def test_config_roundtrip():
    c = client()
    c.post("/api/config/capital", json={"value": "42000000"})
    assert c.get("/api/config/capital").json()["value"] == "42000000"


def _make_position(c, run_id=None):
    return c.post("/api/positions", json={
        "strategy": "rsi", "item_id": 2, "item_name": "Cb",
        "buy_price": 100, "qty": 10, "run_id": run_id,
        "sell_target": 120, "stop_loss": 90,
    }).json()


def test_create_and_list_position():
    c = client()
    p = _make_position(c)
    assert p["state"] == "proposed"
    listed = c.get("/api/positions?state=proposed").json()
    assert len(listed) == 1


def test_position_full_lifecycle():
    c = client()
    rid = c.post("/api/runs", json={"strategy": "rsi", "budget_gp": 10_000}).json()["id"]
    pid = _make_position(c, run_id=rid)["id"]
    assert c.post(f"/api/positions/{pid}/accept").json()["state"] == "accepted"
    assert c.post(f"/api/positions/{pid}/fill").json()["state"] == "filled"
    assert c.post(f"/api/positions/{pid}/sell").json()["state"] == "selling"
    sold = c.post(f"/api/positions/{pid}/sold", json={"sell_price": 120}).json()
    assert sold["state"] == "sold" and sold["realized_pl"] == 180


def test_illegal_transition_409():
    c = client()
    pid = _make_position(c)["id"]
    # cannot fill a proposed position (must accept first)
    assert c.post(f"/api/positions/{pid}/fill").status_code == 409


def test_missing_position_404():
    c = client()
    assert c.post("/api/positions/999/accept").status_code == 404


def test_dismiss_and_cancel():
    c = client()
    pid = _make_position(c)["id"]
    assert c.post(f"/api/positions/{pid}/dismiss").json()["state"] == "dismissed"
    pid2 = _make_position(c)["id"]
    c.post(f"/api/positions/{pid2}/accept")
    assert c.post(f"/api/positions/{pid2}/cancel").json()["state"] == "cancelled"


def test_overview_defaults_zero():
    c = client()
    o = c.get("/api/overview").json()
    assert o["capital"] == 0
    assert o["committed"] == 0
    assert o["free"] == 0
    assert o["open_positions"] == 0
    assert "bond_price" in o and "period_profit" in o


def test_overview_reflects_capital_and_committed():
    c = client()
    c.post("/api/config/capital", json={"value": "1000000"})
    rid = c.post("/api/runs", json={"strategy": "rsi", "budget_gp": 1000000}).json()["id"]
    pid = c.post("/api/positions", json={
        "strategy": "rsi", "item_id": 2, "item_name": "Cb",
        "buy_price": 100, "qty": 100, "run_id": rid}).json()["id"]
    c.post(f"/api/positions/{pid}/accept")   # commits 100*100 = 10_000
    o = c.get("/api/overview").json()
    assert o["capital"] == 1000000
    assert o["committed"] == 10000
    assert o["free"] == 990000
    assert o["open_positions"] == 1


def test_root_serves_dashboard():
    c = client()
    r = c.get("/")
    assert r.status_code == 200
    assert "status-text" in r.text


def test_api_still_works_after_mount():
    c = client()
    assert c.get("/api/strategies").status_code == 200


def test_appjs_served():
    c = client()
    r = c.get("/app.js")
    assert r.status_code == 200
    assert "refresh" in r.text


def test_watchlist_endpoint_reads_config():
    c = client()
    c.post("/api/config/watchlist", json={"value": "4151,11802"})
    r = c.get("/api/watchlist")
    assert r.status_code == 200
    assert r.json()["items"] == [4151, 11802]


def test_watchlist_empty_default():
    c = client()
    assert c.get("/api/watchlist").json()["items"] == []


def test_curate_endpoint_calls_runner():
    from bot import db
    from bot.web import create_app
    from fastapi.testclient import TestClient
    conn = db.connect(":memory:"); db.init_db(conn)
    called = []
    app = create_app(conn, curate_runner=lambda: called.append(True))
    tc = TestClient(app)
    r = tc.post("/api/curate")
    assert r.status_code == 200 and r.json()["status"] == "started"
    assert called == [True]


def test_curate_endpoint_503_when_unconfigured():
    c = client()   # default client() builds app without curate_runner
    assert c.post("/api/curate").status_code == 503
