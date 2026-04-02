@echo off
chcp 65001 >nul 2>&1
set PYTHONUTF8=1
cd /d "%~dp0"
set PYTHONPATH=%CD%
where python >nul 2>&1
if %errorlevel%==0 (
  python start.py
) else (
  py -3 start.py
)
if errorlevel 1 (
  echo.
  echo Если «No module named bot» — запускайте из этой папки: run.cmd или: python -m bot
  echo Если нет BOT_TOKEN — создайте .env по образцу .env.example
  pause
)
