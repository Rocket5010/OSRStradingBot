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
