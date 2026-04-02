@echo off
setlocal
chcp 65001 >nul 2>&1
set PYTHONUTF8=1

pushd "%~dp0" 2>nul
if errorlevel 1 (
  echo Ошибка: не удалось открыть папку скрипта.
  pause
  exit /b 1
)

set PYTHONPATH=%CD%
echo Папка: %CD%
echo Запуск бота... Остановка: Ctrl+C, затем окно останется открытым.
echo Лог: %CD%\bot_run.log
echo.

where python >nul 2>&1
if %errorlevel%==0 (
  python "%~dp0start.py"
) else (
  py -3 "%~dp0start.py"
)

echo.
echo Код выхода: %ERRORLEVEL%
popd
pause
endlocal
