from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

_LOG_FILE = Path(__file__).resolve().parent.parent / "bot_run.log"


def _configure_logging() -> None:
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s:%(name)s:%(message)s")
    for h in root.handlers[:]:
        root.removeHandler(h)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(sh)
    try:
        fh = logging.FileHandler(_LOG_FILE, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except OSError as e:
        logging.getLogger(__name__).warning("Не удалось писать %s: %s", _LOG_FILE, e)


def load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    root = Path(__file__).resolve().parent.parent
    load_dotenv(root / ".env")


async def run_polling() -> None:
    load_env()
    _configure_logging()
    log = logging.getLogger(__name__)
    log.info("Лог также пишется в файл: %s", _LOG_FILE.resolve())

    token = (os.environ.get("BOT_TOKEN") or "").strip()
    if not token:
        raise SystemExit(
            "BOT_TOKEN не задан. Скопируйте .env.example в .env в этой папке проекта "
            "и добавьте BOT_TOKEN=... (токен от @BotFather).\n"
            "Проверка без Telegram: python -m bot --smoke-sources"
        )

    from bot.handlers.exclusive import router

    bot = Bot(token=token)
    me = await bot.get_me()
    log.info("Polling started as @%s (id=%s)", me.username, me.id)
    log.info(
        "При повторяющемся TelegramConflictError в логе — с тем же BOT_TOKEN уже "
        "работает другой процесс (окно, Fly.io и т.д.); остановите его."
    )

    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    try:
        await dp.start_polling(bot)
    except Exception:
        logging.getLogger(__name__).exception("Ошибка в polling (см. также %s)", _LOG_FILE)
        raise
