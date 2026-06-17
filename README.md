# OSRS Flip Bot

Local web dashboard that advises buy/sell decisions in the OSRS Grand
Exchange. **It never trades in-game** — it proposes, you click in the GE.

## Run
```
pip install -r requirements.txt
python -m bot.main          # then open http://127.0.0.1:8000
```
Or double-click `start-bot.bat` (Windows, no console window).

Set your contact in the `OSRS_BOT_UA` environment variable (the OSRS Wiki API
asks for it).

## Auto-start at login (optional)
Press `Win+R`, type `shell:startup`, and drop a shortcut to `start-bot.bat`
there. The bot then runs from login; just open the dashboard bookmark.

## Notifications (optional)
Set a Discord webhook URL:
```
curl -X POST http://127.0.0.1:8000/api/config/notify_webhook -H "Content-Type: application/json" -d "{\"value\":\"https://discord.com/api/webhooks/...\"}"
```

## Tests
```
python -m pytest
```

## How it works
See the Obsidian vault under `Bot vault/` (start at `Home.md`).
