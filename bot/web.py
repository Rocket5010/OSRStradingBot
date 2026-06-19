# bot/web.py
"""FastAPI JSON API. create_app(conn) closes over a sqlite connection so
tests can pass an in-memory DB. Presentation-agnostic — returns plain JSON."""

import os
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from bot import db as db_mod
from bot import runs as runs_mod
from bot import positions as pos_mod
from bot.strategies.loader import load_strategies


_OPEN = ("accepted", "filled", "selling")


def _row(r):
    return dict(r) if r is not None else None


class StartRunBody(BaseModel):
    strategy: str
    budget_gp: int
    params: dict = {}


class ConfigBody(BaseModel):
    value: str


class CreatePositionBody(BaseModel):
    strategy: str
    item_id: int
    item_name: str
    buy_price: int
    qty: int
    run_id: int | None = None
    sell_target: int | None = None
    stop_loss: int | None = None


class SellBody(BaseModel):
    sell_price: int


def create_app(conn, strategies_dir=None, curate_runner=None):
    app = FastAPI(title="OSRS Flip Bot")
    sdir = os.path.abspath(
        strategies_dir or os.path.join(os.path.dirname(__file__), "strategies"))

    @app.get("/api/strategies")
    def list_strategies():
        found = load_strategies(sdir)
        return [{"name": n, "description": s.description,
                 "default_params": s.default_params()}
                for n, s in found.items()]

    @app.get("/api/runs")
    def list_runs():
        return [_row(r) for r in runs_mod.list_runs(conn)]

    @app.post("/api/runs")
    def start_run(body: StartRunBody):
        rid = runs_mod.start_run(conn, body.strategy, body.budget_gp, body.params)
        return _row(runs_mod.get_run(conn, rid))

    @app.post("/api/runs/{run_id}/stop")
    def stop_run(run_id: int):
        if runs_mod.get_run(conn, run_id) is None:
            raise HTTPException(status_code=404, detail="run not found")
        runs_mod.stop_run(conn, run_id)
        return _row(runs_mod.get_run(conn, run_id))

    @app.get("/api/config/{key}")
    def get_config(key: str):
        return {"key": key, "value": db_mod.get_config(conn, key)}

    @app.post("/api/config/{key}")
    def set_config(key: str, body: ConfigBody):
        db_mod.set_config(conn, key, body.value)
        return {"key": key, "value": body.value}

    @app.get("/api/positions")
    def list_positions(state: str | None = None):
        return [_row(r) for r in pos_mod.list_positions(conn, state)]

    @app.post("/api/positions")
    def create_position(body: CreatePositionBody):
        pid = pos_mod.create_proposed(
            conn, strategy=body.strategy, item_id=body.item_id,
            item_name=body.item_name, buy_price=body.buy_price, qty=body.qty,
            run_id=body.run_id, sell_target=body.sell_target,
            stop_loss=body.stop_loss)
        return _row(pos_mod.get(conn, pid))

    def _transition(pid, fn, *args):
        if pos_mod.get(conn, pid) is None:
            raise HTTPException(status_code=404, detail="position not found")
        try:
            fn(conn, pid, *args)
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        return _row(pos_mod.get(conn, pid))

    @app.post("/api/positions/{pid}/accept")
    def accept_position(pid: int):
        return _transition(pid, pos_mod.accept)

    @app.post("/api/positions/{pid}/fill")
    def fill_position(pid: int):
        return _transition(pid, pos_mod.mark_filled)

    @app.post("/api/positions/{pid}/sell")
    def sell_position(pid: int):
        return _transition(pid, pos_mod.start_selling)

    @app.post("/api/positions/{pid}/sold")
    def sold_position(pid: int, body: SellBody):
        return _transition(pid, pos_mod.mark_sold, body.sell_price)

    @app.post("/api/positions/{pid}/cancel")
    def cancel_position(pid: int):
        return _transition(pid, pos_mod.cancel)

    @app.post("/api/positions/{pid}/dismiss")
    def dismiss_position(pid: int):
        return _transition(pid, pos_mod.dismiss)

    @app.get("/api/overview")
    def overview():
        def cfg_int(key, default=0):
            v = db_mod.get_config(conn, key)
            return int(v) if v is not None else default

        capital = cfg_int("capital")
        committed_row = conn.execute(
            "SELECT COALESCE(SUM(buy_price * qty), 0) AS s FROM positions "
            f"WHERE state IN ({','.join('?' * len(_OPEN))})", _OPEN).fetchone()
        committed = committed_row["s"]
        open_count = conn.execute(
            f"SELECT COUNT(*) AS c FROM positions WHERE state IN "
            f"({','.join('?' * len(_OPEN))})", _OPEN).fetchone()["c"]
        # No goal period started yet -> 0 profit (don't count all-time history).
        period_start = db_mod.get_config(conn, "goal_period_start")
        if period_start:
            profit_row = conn.execute(
                "SELECT COALESCE(SUM(realized_pl), 0) AS s FROM positions "
                "WHERE state='sold' AND closed_at >= ?", (period_start,)).fetchone()
            period_profit = profit_row["s"]
        else:
            period_profit = 0
        bond_price = cfg_int("bond_price", 0)
        return {
            "capital": capital,
            "committed": committed,
            "free": capital - committed,
            "open_positions": open_count,
            "period_profit": period_profit,
            "bond_price": bond_price,
            "bond_days": cfg_int("bond_days", 14),
            "goal_progress": (period_profit / bond_price) if bond_price else 0.0,
        }

    @app.get("/api/watchlist")
    def get_watchlist():
        from bot.curator import get_watchlist as _gw
        return {"items": _gw(conn)}

    @app.post("/api/curate")
    def curate_now_trigger():
        if curate_runner is None:
            raise HTTPException(status_code=503, detail="curation not available")
        curate_runner()
        return {"status": "started"}

    static_dir = os.path.join(os.path.dirname(__file__), "static")
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    return app
