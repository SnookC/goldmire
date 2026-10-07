@echo off
cd /d "%~dp0"
if not exist ".env" copy env_template.txt .env >nul
notepad .env
