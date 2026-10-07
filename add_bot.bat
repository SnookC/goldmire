@echo off
cd /d "%~dp0"
title Add a trading bot
if not exist ".venv" (
  echo Run 1_setup.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" add_bot.py
pause
