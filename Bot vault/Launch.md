# Launch (CMD-free)

The user never touches the command line. Built in [[Build Phases|Phase 6]].

1. **One-click `.bat`/shortcut** — starts the process hidden, opens the dashboard in the browser. No CMD window.
2. **Auto-start at Windows login** (optional) — Task Scheduler / startup folder. Runs from login; user just opens the dashboard bookmark.
3. **Cloud — Oracle Free VM** — always on, 24/7; your PC need not be on. Step-by-step beginner guide: [[Deploy to Oracle Cloud]] (Arm A1 instance + systemd auto-restart + SSH tunnel for private access). Rehearse it risk-free first: [[Practice in a Local VM]]. Enabled by the host-agnostic [[Architecture Overview|one-process design]] and [[Constraints|free-only]] rule.

`OSRS_BOT_HOST` / `OSRS_BOT_PORT` env vars control the bind address (default `127.0.0.1:8000`); set `OSRS_BOT_HOST=0.0.0.0` for local-VM browser access only.
