@echo off
cd /d "%~dp0"
title Goldmire - close this window to stop the bots
if not exist ".venv" (
  echo Run 1_setup.bat first.
  pause
  exit /b 1
)
:start
".venv\Scripts\python.exe" bot.py %*
rem Exit code 3 = an update was just installed: start the new version.
if errorlevel 3 if not errorlevel 4 (
  echo.
  echo Starting the updated Goldmire...
  goto start
)
pause
