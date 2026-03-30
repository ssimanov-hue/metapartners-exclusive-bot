from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from aiogram import Bot, Dispatcher


def load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    root = Path(__file__).resolve().parent.parent
    load_dotenv(root / ".env")


async def run_polling() -> None:
    load_env()
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s:%(name)s:%(message)s",
    )
    token = (os.environ.get("BOT_TOKEN") or "").strip()
    if not token:
        raise SystemExit(
            "BOT_TOKEN не задан. Скопируйте .env.example в .env в этой папке проекта "
            "и добавьте BOT_TOKEN=... (токен от @BotFather).\n"
            "Проверка без Telegram: python -m bot --smoke-sources"
        )

    from bot.handlers.exclusive import router

    bot = Bot(token=token)
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)
