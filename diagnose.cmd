@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
echo === Диагностика Metapartners bot ===
echo Папка: %CD%
echo.

set PYTHONPATH=%CD%

where python >nul 2>&1
if %errorlevel%==0 (
  python --version
  echo.
  python -c "import bot; print('Импорт пакета bot: OK')"
  if errorlevel 1 goto :fail
  python -c "from dotenv import load_dotenv; import os; load_dotenv(); t=(os.environ.get('BOT_TOKEN')or'').strip(); print('BOT_TOKEN:', 'задан' if t else 'НЕТ — бот сразу выйдет')"
  goto :done
)

py -3 --version
echo.
py -3 -c "import bot; print('Импорт пакета bot: OK')"
if errorlevel 1 goto :fail
py -3 -c "from dotenv import load_dotenv; import os; load_dotenv(); t=(os.environ.get('BOT_TOKEN')or'').strip(); print('BOT_TOKEN:', 'задан' if t else 'НЕТ — бот сразу выйдет')"
goto :done

:fail
echo.
echo Ошибка. Выполните: pip install -r requirements.txt
goto :end

:done
echo.
echo.
echo Дополнительно: python -m bot --doctor  ^(проверка Telegram API^)
echo Если всё OK: run.cmd или python -m bot из этой папки

:end
pause
