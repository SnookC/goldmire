@echo off
cd /d "%~dp0"
title Goldmire - The Hero Trials
if not exist ".venv" (
  echo Run 1_setup.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" hero_test.py %*
pause
