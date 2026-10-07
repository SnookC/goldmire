@echo off
cd /d "%~dp0"
echo === Setting up the Alpaca bot (one time only) ===
echo.

where py >nul 2>nul
if %errorlevel%==0 (set PY=py -3) else (set PY=python)

%PY% --version
if errorlevel 1 (
  echo ERROR: Python was not found. Tell Claude you saw this message.
  pause
  exit /b 1
)

if not exist ".venv" (
  echo Creating a private Python environment...
  %PY% -m venv .venv
)

echo Installing packages (takes a minute)...
".venv\Scripts\python.exe" -m pip install --upgrade pip -q
".venv\Scripts\python.exe" -m pip install -r requirements.txt -q
if errorlevel 1 (
  echo ERROR: package install failed. Tell Claude what you see above.
  pause
  exit /b 1
)

if not exist ".env" (
  copy env_template.txt .env >nul
  echo Created your .env key file.
)

echo.
echo === SETUP DONE ===
echo Next: double-click 2_check_connection.bat AFTER you paste your keys into .env
echo.
pause
