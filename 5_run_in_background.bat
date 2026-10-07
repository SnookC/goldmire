@echo off
cd /d "%~dp0"
if not exist ".venv" (
  echo Run 1_setup.bat first.
  pause
  exit /b 1
)
rem Starts Goldmire in the background: look for its icon by the clock.
start "" ".venv\Scripts\pythonw.exe" goldmire_tray.py %*
