# bot/web.py
"""FastAPI JSON API. create_app(conn) closes over a sqlite connection so
tests can pass an in-memory DB. Presentation-agnostic — returns plain JSON."""

import os
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from bot import db as db_mod
from bot import runs as runs_mod
from bot import positions as pos_mod
from bot.strategies.loader import load_strategies


_OPEN = ("accepted", "filled", "selling")
# states where capital is committed to an order that may never fill
_PENDING = ("accepted", "selling")


def _row(r):
    return dict(r) if r is not None else None


def _parse_iso(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _age_basis(d):
    """Timestamp the current state started from, for age/staleness."""
    state = d.get("state")
    if state == "accepted":
        return d.get("accepted_at") or d.get("created_at")
    if state == "selling":
        return d.get("filled_at") or d.get("accepted_at") or d.get("created_at")
    if state == "filled":
        return d.get("filled_at")
    return d.get("created_at")


def _enrich(d, now_dt, stale_hours):
    """Add age_hours + stale to a position dict. stale flags pending orders
    (accepted/selling) that have sat past the threshold — capital frozen in an
    order that isn't filling, the user should cancel or re-price."""
    started = _parse_iso(_age_basis(d))
    if started is not None:
        age_h = (now_dt - started).total_seconds() / 3600.0
        d["age_hours"] = round(age_h, 1)
        d["stale"] = d.get("state") in _PENDING and age_h >= stale_hours
    else:
        d["age_hours"] = None
        d["stale"] = False
    return d


class StartRunBody(BaseModel):
    strategy: str
    budget_gp: int = Field(gt=0)
    params: dict = {}


class ConfigBody(BaseModel):
    value: str


class CreatePositionBody(BaseModel):
    strategy: str
    item_id: int = Field(gt=0)
    item_name: str
    buy_price: int = Field(gt=0)
    qty: int = Field(gt=0)
    run_id: int | None = None
    sell_target: int | None = None
    stop_loss: int | None = None


class SellBody(BaseModel):
    sell_price: int = Field(gt=0)


def create_app(conn, strategies_dir=None, curate_runner=None, curation_status=None, backtest_runner=None, backtest_status=None):
    from bot.curation_status import CurationStatus
    status = curation_status or CurationStatus()
    bt_status = backtest_status or CurationStatus()
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
        stale_hours = float(db_mod.get_config(conn, "order_stale_hours") or "24")
        now_dt = datetime.now(timezone.utc)
        return [_enrich(_row(r), now_dt, stale_hours)
                for r in pos_mod.list_positions(conn, state)]

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
        # stale pending orders: capital frozen in buys/sells that aren't filling
        stale_hours = float(db_mod.get_config(conn, "order_stale_hours") or "24")
        now_dt = datetime.now(timezone.utc)
        stale_orders, frozen_gp = 0, 0
        for r in conn.execute(
                "SELECT * FROM positions WHERE state IN ('accepted','selling')"
                ).fetchall():
            d = _enrich(dict(r), now_dt, stale_hours)
            if d["stale"]:
                stale_orders += 1
                frozen_gp += (r["buy_price"] or 0) * (r["qty"] or 0)

        bond_price = cfg_int("bond_price", 0)
        auto_rows = conn.execute(
            "SELECT strategy FROM strategy_runs WHERE auto=1 AND state='running' "
            "ORDER BY id").fetchall()
        active = [r["strategy"] for r in auto_rows]
        dd_pct = float(db_mod.get_config(conn, "max_drawdown_stop_pct") or "0")
        drawdown_halt = (dd_pct > 0 and capital > 0
                         and period_profit < -(dd_pct / 100.0) * capital)
        return {
            "capital": capital,
            "active_strategy": active[0] if active else None,
            "active_strategies": active,
            "drawdown_halt": drawdown_halt,
            "committed": committed,
            "free": capital - committed,
            "open_positions": open_count,
            "stale_orders": stale_orders,
            "frozen_gp": frozen_gp,
            "period_profit": period_profit,
            "bond_price": bond_price,
            "bond_days": cfg_int("bond_days", 14),
            "goal_progress": (period_profit / bond_price) if bond_price else 0.0,
        }

    @app.get("/api/watchlist")
    def get_watchlist():
        from bot.curator import get_watchlist as _gw
        names = db_mod.get_item_names(conn)
        return {"items": [{"id": i, "name": names.get(i, str(i))}
                          for i in _gw(conn)]}

    @app.post("/api/curate")
    def curate_now_trigger():
        if curate_runner is None:
            raise HTTPException(status_code=503, detail="curation not available")
        curate_runner()
        return {"status": "started"}

    @app.get("/api/curate/status")
    def curate_status():
        return status.snapshot()

    @app.post("/api/reset")
    def reset():
        db_mod.reset_state(conn)
        return {"status": "reset"}

    @app.get("/api/backtest")
    def backtest_result():
        from bot.backtest_rank import get_ranking
        return get_ranking(conn)

    @app.get("/api/backtest/status")
    def backtest_status_ep():
        return bt_status.snapshot()

    @app.post("/api/backtest/run")
    def backtest_run():
        if backtest_runner is None:
            raise HTTPException(status_code=503, detail="backtest not available")
        backtest_runner()
        return {"status": "started"}

    static_dir = os.path.join(os.path.dirname(__file__), "static")
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    return app
