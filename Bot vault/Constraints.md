# Constraints

The rules that shape every decision in [[Home|the project]].

## No in-game automation
There is no public API to buy/sell in the Grand Exchange. Auto-clicking the game client is **botting → account ban**. The bot is an **advisor only**: it decides, the user performs the physical GE clicks. See [[Position Lifecycle]] — the user drives state transitions.

## Free only
No paid services. The [[OSRS Wiki API]] is free with no monthly quota. Compute stays within an always-on free tier — local PC now, Oracle Cloud Free VM later (see [[Launch]]). This is why [[Architecture Overview|the architecture]] is one cheap process, not metered cloud functions.

## Poll cadence = 5 min
The `/5m` aggregate is recomputed every 5 minutes; polling faster yields identical data. Configurable but never faster than data granularity. Drives the [[Modules|poller]].

## Bot = brain, user = hand
The bot makes every decision (what, when, price). The user never analyzes — only accepts in the dashboard and places the order. See [[Strategy System]].
