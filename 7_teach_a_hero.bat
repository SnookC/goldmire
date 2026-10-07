@echo off
cd /d "%~dp0"
title Goldmire - Teach a hero a strategy
if not exist ".venv" (
  echo Run 1_setup.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" promote.py
pause
