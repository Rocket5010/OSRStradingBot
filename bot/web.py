# bot/web.py
"""FastAPI JSON API. create_app(conn) closes over a sqlite connection so
tests can pass an in-memory DB. Presentation-agnostic — returns plain JSON."""

import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from bot import db as db_mod
from bot import runs as runs_mod
from bot import positions as pos_mod
from bot.strategies.loader import load_strategies


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


def create_app(conn, strategies_dir=None):
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

    return app
