@echo off
cd /d "%~dp0"
if not exist ".venv" (
  echo Run 1_setup.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" check_connection.py
pause
