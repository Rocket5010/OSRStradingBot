@echo off
REM One-click launcher for the OSRS Flip Bot. Starts the server hidden and
REM opens the dashboard. Set OSRS_BOT_UA to your own contact before sharing.
cd /d "%~dp0"
if "%OSRS_BOT_UA%"=="" set OSRS_BOT_UA=osrs-flip-bot/1.0 (rocket5010)
REM Run hidden but redirect output to bot.log so startup errors are visible
REM (pythonw normally discards them). If the dashboard doesn't load, open bot.log.
start "" /b pythonw -m bot.main > bot.log 2>&1
timeout /t 3 /nobreak >nul
start "" http://127.0.0.1:8000
