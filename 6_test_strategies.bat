@echo off
cd /d "%~dp0"
title Goldmire - The Proving Grounds
if not exist ".venv" (
  echo Run 1_setup.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" backtest.py %*
pause
