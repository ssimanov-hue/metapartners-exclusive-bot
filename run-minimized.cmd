@echo off
chcp 65001 >nul 2>&1
set PYTHONUTF8=1
REM Запуск бота в отдельном окне (свёрнутом). Не зависит от Cursor — можно из Проводника или ярлыка.
cd /d "%~dp0"
set PYTHONPATH=%~dp0
where python >nul 2>&1
if %errorlevel%==0 (
  start "Metapartners bot" /min cmd /k "chcp 65001>nul & cd /d ""%~dp0"" & set PYTHONUTF8=1 & set PYTHONPATH=%~dp0 & python start.py"
) else (
  start "Metapartners bot" /min cmd /k "chcp 65001>nul & cd /d ""%~dp0"" & set PYTHONUTF8=1 & set PYTHONPATH=%~dp0 & py -3 start.py"
)
