@echo off
REM One-click launcher for the OSRS Flip Bot. Starts the server hidden and
REM opens the dashboard. Set OSRS_BOT_UA to your own contact before sharing.
cd /d "%~dp0"
if "%OSRS_BOT_UA%"=="" set OSRS_BOT_UA=osrs-flip-bot/1.0 (set OSRS_BOT_UA)
start "" /b pythonw -m bot.main
timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:8000
