@echo off
cd /d "%~dp0"
title Goldmire - News replay (word list vs FinBERT)
if not exist ".venv" (
  echo Run 1_setup.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" news_replay.py
pause
