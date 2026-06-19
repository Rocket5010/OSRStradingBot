# OSRS Flip Bot

A local web app that finds buy/sell opportunities in the Old School RuneScape
Grand Exchange and tells you exactly what to do — you place the trades.

> **Bot = brain, you = hand.** It **never trades in-game.** There is no public
> API to buy/sell in the GE, and auto-clicking the game client is botting and
> gets your account banned. This tool only *advises*: it proposes, you click in
> the GE. 100% within the rules.

It runs entirely on your machine, uses only the free
[OSRS Wiki real-time prices API](https://prices.runescape.wiki/), and costs
nothing to run.

---

## What it does

1. **Polls** live GE prices every 5 minutes.
2. **Runs strategies** you start manually, each with its own gp budget.
3. **Proposes buys** within budget and **recommends sells** (target margin +
   stop-loss + max hold time).
4. Shows it all in a **dark + gold dashboard** — accept a buy, mark it filled,
   sell, or cancel, each with one click.
5. Optional **webhook notifications** (Discord) push signals to your phone.
6. Tracks a **bond goal** — progress toward one bond (~14M gp) every 14 days.

Two families of strategy are included: **active flipping** (`margin_flip`) and
**investing** (`mean_reversion`, `bollinger`, `rsi`, `crash_recovery`,
`ma_crossover`, `momentum`, `breakout`). A backtester ranks them over historical
data so you can pick the best one before risking gp.

---

## Quick start

```bash
pip install -r requirements.txt
python -m bot.main          # then open http://127.0.0.1:8000
```

Or on Windows just double-click **`start-bot.bat`** (no console window, opens the
dashboard automatically).

Set your contact in the `OSRS_BOT_UA` environment variable — the OSRS Wiki API
asks callers to identify themselves:

```bash
set OSRS_BOT_UA=osrs-flip-bot/1.0 (you@example.com)     # Windows
export OSRS_BOT_UA="osrs-flip-bot/1.0 (you@example.com)" # macOS/Linux
```

---

## Using it

1. Open the dashboard at <http://127.0.0.1:8000>.
2. Set your capital (optional, drives the overview/free-budget numbers):
   ```bash
   curl -X POST http://127.0.0.1:8000/api/config/capital \
     -H "Content-Type: application/json" -d "{\"value\":\"50000000\"}"
   ```
3. Pick a strategy, enter a gp budget, click **Start**.
4. When the bot proposes a buy, click **Accept**, place that order in the GE,
   then click **Filled** once it fills.
5. When the bot recommends a sell, click **Sell**, place the sell in the GE,
   then **Sold** (enter the price). P/L is recorded against the strategy's run.
6. Use **Cancel** for any order that doesn't fill in-game.

---

## Notifications (optional)

Get pinged on Discord when the bot proposes a buy or recommends a sell:

```bash
curl -X POST http://127.0.0.1:8000/api/config/notify_webhook \
  -H "Content-Type: application/json" \
  -d "{\"value\":\"https://discord.com/api/webhooks/...\"}"
```

---

## Auto-start at login (optional)

Press `Win+R`, type `shell:startup`, and drop a shortcut to `start-bot.bat`
there. The bot then runs from login — just open the dashboard bookmark whenever
you want to check it.

---

## Architecture

One Python process (stdlib + FastAPI). The frontend talks to the backend only
over a JSON API, so the UI can be restyled without touching any Python.

```
bot/
├── api_client.py        # OSRS Wiki API client (rate-limited)
├── db.py                # SQLite schema + helpers
├── poller.py            # one poll cycle -> price_cache
├── tax.py               # GE 2% sell tax
├── runs.py              # strategy runs (start/stop + budget)
├── positions.py         # position lifecycle + P/L
├── market.py            # assemble MarketData + position adapter
├── engine_live.py       # the decision pass (buys + sell recs)
├── scheduler.py         # 5-min background loop (own db connection)
├── notify.py            # webhook notifications
├── goal.py              # bond-price / goal-period refresh
├── web.py               # FastAPI JSON API + serves the dashboard
├── main.py              # entry point
├── static/              # dashboard (index.html, style.css, app.js)
├── strategies/          # Strategy contract + 8 pluggable strategies
└── backtest/            # walk-forward engine, metrics, ranking, runner
```

### Adding your own strategy

Drop a `.py` file in `bot/strategies/` with a class subclassing `Strategy`
(`find_buys`, `should_sell`, `default_params`). It is auto-discovered and shows
up in the dashboard dropdown — no other code changes needed.

---

## Backtesting

Rank all strategies over real historical data before trusting one:

```python
from bot.api_client import WikiClient
from bot.strategies.loader import load_strategies
from bot.backtest.runner import run_ranking, format_ranking

client = WikiClient(user_agent="osrs-flip-bot/1.0 (you@example.com)")
factories = {n: type(s) for n, s in
             load_strategies("bot/strategies").items()}
ranked = run_ranking(client, item_id=4151, factories=factories,
                     budget=50_000_000, timestep="24h")
print(format_ranking(ranked))
```

Backtest results are **guidance, not gospel** — GE data has no order-book
depth, so fills are assumed (conservatively).

---

## Updating

Pull the latest after the repo changes — **stop → pull → reinstall → restart**:

```bash
# stop the running bot first (it locks the DB on Windows)
git pull
pip install -r requirements.txt
# restart (start-bot.bat or: python -m bot.main)
```

Your `osrs_bot.db` is migrated automatically on start (new columns added in
place), so logged positions and settings survive. Full per-platform steps:
`Bot vault/Updating the Bot.md`.

## Tests

```bash
python -m pytest
```

---

## Limitations

- Prices update ~every 5 minutes (the API's granularity) — this suits slow
  flips and investing, not millisecond arbitrage.
- No live order-book depth, so fills aren't guaranteed.
- GE buy limits (per 4h) and the 2% sell tax are accounted for.

---

## Full documentation

The design spec, architecture notes, strategy details, and per-phase
implementation plans live in the Obsidian vault under `Bot vault/` — start at
`Bot vault/Home.md`.
