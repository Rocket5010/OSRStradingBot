# 🪙 OSRS Flip Bot — Home

Map of Content (MOC). Start here. Open the **graph view** to see how everything connects.

> Local web dashboard powered by one Python process. Polls the OSRS Wiki API, runs pluggable strategies, proposes capital-aware buy/sell signals. **Bot = brain, user = hand.** Never auto-trades in-game.

## 🧭 Core
- [[OSRS Flip Bot Design Spec]] — the full approved spec
- [[Constraints]] — the rules that shape everything (no botting, free-only)
- [[Conventions]] — language, naming

## 🏗️ How it works
- [[Architecture Overview]] — the one-process design
- [[Modules]] — every code unit and its job
- [[Data Model]] — what's stored in SQLite
- [[Position Lifecycle]] — proposed → sold state machine
- [[GE Tax and PL]] — how profit is calculated

## 🧠 Strategies
- [[Strategy System]] — the plugin contract + how to add one
- Active: [[margin_flip]]
- Mean-reversion: [[mean_reversion]] · [[bollinger]] · [[rsi]] · [[crash_recovery]]
- Trend/momentum: [[ma_crossover]] · [[momentum]] · [[breakout]]
- [[Backtesting]] — find the best strategy
- [[Watchlist Curator]] — auto-find new items to watch
- [[Auto-pilot]] — bot auto-runs the best-ranked strategy

## 🌐 External
- [[OSRS Wiki API]] — the free data source
- [[Bond Goal]] — the success metric (~1 bond / 14 days)

## 🛡️ Quality
- [[Audit and Hardening]] — full code audit + fixes (156 tests)

## 🚀 Running & updating
- [[Launch]] — start the bot (local + cloud)
- [[Updating the Bot]] — pull the latest from GitHub
- [[Deploy to Oracle Cloud]] · [[Practice in a Local VM]]

## 🚧 Building it
- [[Build Phases]] — phased plan, MVP = phases 1–3
- [[Launch]] — CMD-free start

## 📌 Status
Design approved. Next: implementation plan. MVP = [[Build Phases|phases 1–3]].
