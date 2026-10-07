@echo off
cd /d "%~dp0"
chcp 65001 >nul
title Goldmire - phone access
if not exist ".venv" (
  echo Run 1_setup.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" phone_access.py %*
pause
