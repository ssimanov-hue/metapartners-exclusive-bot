from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot.services.aggregator import collect_exclusives_for_day
from bot.services.messages import build_telegram_chunks
from bot.sources.http_utils import create_client

logger = logging.getLogger(__name__)

router = Router(name="exclusive")


def default_tz() -> str:
    return os.environ.get("DEFAULT_TZ", "Europe/Moscow").strip() or "Europe/Moscow"


async def _send_day_report(message: Message, day: date, tz_name: str) -> None:
    try:
        async with create_client() as http:
            items, results = await collect_exclusives_for_day(day, tz_name, http)
        failed = [r.source_id for r in results if r.error]
        chunks = build_telegram_chunks(day, tz_name, items, failed)
    except Exception:
        logger.exception("collect_exclusives_for_day failed")
        await message.answer(
            "Сейчас не удалось получить эксклюзивы. Попробуйте чуть позже."
        )
        return
    for part in chunks:
        await message.answer(part, parse_mode="HTML", disable_web_page_preview=True)


@router.message(Command("start"), F.chat.type == "private")
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Команды (только в личных сообщениях):\n"
        "/today — эксклюзивы за сегодня\n"
        "/yesterday — за вчера\n"
        "/day ГГГГ-ММ-ДД — за указанную дату\n\n"
        f"Часовой пояс: {default_tz()}"
    )


@router.message(Command("today"), F.chat.type == "private")
async def cmd_today(message: Message) -> None:
    tz_name = default_tz()
    try:
        zi = ZoneInfo(tz_name)
    except Exception:
        await message.answer("Некорректный DEFAULT_TZ в настройках.")
        return
    d = datetime.now(zi).date()
    await _send_day_report(message, d, tz_name)


@router.message(Command("yesterday"), F.chat.type == "private")
async def cmd_yesterday(message: Message) -> None:
    tz_name = default_tz()
    try:
        zi = ZoneInfo(tz_name)
    except Exception:
        await message.answer("Некорректный DEFAULT_TZ в настройках.")
        return
    d = datetime.now(zi).date() - timedelta(days=1)
    await _send_day_report(message, d, tz_name)


@router.message(Command("day"), F.chat.type == "private")
async def cmd_day(message: Message, command: CommandObject) -> None:
    if not command.args:
        await message.answer("Формат: /day 2026-03-29")
        return
    arg0 = command.args.strip().split()[0]
    try:
        d = date.fromisoformat(arg0)
    except ValueError:
        await message.answer(
            "Неверная дата. Укажите ГГГГ-ММ-ДД, например: /day 2026-03-29"
        )
        return
    tz_name = default_tz()
    try:
        ZoneInfo(tz_name)
    except Exception:
        await message.answer("Некорректный DEFAULT_TZ в настройках.")
        return
    await _send_day_report(message, d, tz_name)
