@echo off
cd /d "%~dp0"
title Goldmire - Proving Grounds (wide test: gap-and-hold drift)
if not exist ".venv" (
  echo Run 1_setup.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" backtest.py gap --wide
pause
