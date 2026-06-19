# Updating the Bot

How to pull the latest code from GitHub after it's been updated. You've already
run it once, so this is the *update* path, not first install. Part of [[Home]].

> **Your data is safe.** `init_db` auto-migrates the database — new columns are
> added to your existing `osrs_bot.db` on the next start, so your logged
> positions and settings survive. You do **not** need to delete the database.
> (If you ever *want* a clean slate, stop the bot and delete `osrs_bot.db*`.)

The pattern is always the same: **stop → pull → reinstall deps → restart.**

---

## Windows (run with start-bot.bat / python)

1. **Stop the bot.** Close the dashboard tab, then stop the process. In
   PowerShell:
```powershell
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*bot.main*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```
   (Stopping matters on Windows — a running bot locks the database files.)

2. **Pull + reinstall** in the repo folder (PowerShell):
```powershell
cd "C:\Users\sande\.claude\Claude code\OSRS invester"
git pull
pip install -r requirements.txt
```

3. **Restart**: double-click `start-bot.bat` (or `python -m bot.main`).

> If `git pull` complains about local changes you didn't make (often just line
> endings), run `git stash` first, pull, then `git stash drop`. Runtime files
> (`osrs_bot.db*`, `bot.log`) are git-ignored and never conflict.

---

## WSL2 / local Linux VM

```bash
cd ~/OSRStradingBot          # the Linux home, not /mnt/c — see Practice in a Local VM
# stop it: Ctrl+C if running in the terminal, or if you set up systemd:
sudo systemctl stop osrsbot
git pull
.venv/bin/pip install -r requirements.txt
# restart:
sudo systemctl start osrsbot     # or: .venv/bin/python -m bot.main
```

---

## Cloud (Oracle VM)

Same as [[Deploy to Oracle Cloud]] §6:
```bash
cd ~/OSRStradingBot
git pull
.venv/bin/pip install -r requirements.txt
sudo systemctl restart osrsbot
```
The `systemctl restart` stops and starts in one step, so no manual process kill.

---

## After updating — quick check
- Dashboard loads at `http://localhost:8000` (or your tunnel).
- Windows: if it doesn't load, open `bot.log` for the error ([[Launch]]).
- Linux: `journalctl -u osrsbot -f` shows live logs.
