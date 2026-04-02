"""Run: python -m bot  |  python -m bot --smoke-sources  |  python -m bot --doctor"""

from __future__ import annotations

import argparse
import asyncio
import sys
import traceback


def _cmd_doctor() -> None:
    """Проверка .env, импортов и ответа Telegram без запуска polling."""
    from pathlib import Path

    from bot.main import load_env

    root = Path(__file__).resolve().parent.parent
    load_env()
    env_path = root / ".env"
    print(f"Папка проекта: {root}")
    print(f"Файл .env: {'есть' if env_path.is_file() else 'НЕТ — создайте из .env.example'}")
    import os

    token = (os.environ.get("BOT_TOKEN") or "").strip()
    if not token:
        print("BOT_TOKEN: не задан")
        raise SystemExit(1)
    tail = token[-6:] if len(token) > 6 else "****"
    print(f"BOT_TOKEN: задан (…{tail})")

    async def ping() -> None:
        from aiogram import Bot

        bot = Bot(token=token)
        try:
            me = await bot.get_me()
            print(f"Telegram API: OK, бот @{me.username} (id={me.id})")
        finally:
            await bot.session.close()

    asyncio.run(ping())
    print("Запуск polling: python -m bot  или  start.py / run.cmd")


def main() -> None:
    parser = argparse.ArgumentParser(description="Metapartners exclusive Telegram bot")
    parser.add_argument(
        "--smoke-sources",
        action="store_true",
        help="Only fetch all sources (no Telegram)",
    )
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="Проверить .env, BOT_TOKEN и связь с Telegram (без polling)",
    )
    args = parser.parse_args()

    if args.doctor:
        _cmd_doctor()
        return

    if args.smoke_sources:
        from bot.main import load_env
        from bot.sources.registry import _main_sync

        load_env()
        _main_sync()
        return

    from bot.main import run_polling

    asyncio.run(run_polling())


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
    except SystemExit:
        raise
    except BaseException as e:
        print(f"\nОшибка запуска: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
