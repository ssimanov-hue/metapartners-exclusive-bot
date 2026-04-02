from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.enums import ChatAction
from aiogram.filters import Filter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.aggregator import collect_exclusives_for_day
from bot.services.messages import build_telegram_chunks
from bot.sources.http_utils import create_client

logger = logging.getLogger(__name__)

# Сбор со всех источников + фильтр по суткам Москвы; на медленной сети без лимита
# обработка update может «висеть» бесконечно.
_COLLECT_TIMEOUT_SEC = 150.0

router = Router(name="exclusive")

# «Сегодня» / «Вчера»: календарный день и окно [00:00; 24:00) всегда по Москве,
# чтобы свежие российские новости не выпадали из-за другого DEFAULT_TZ в .env.
MOSCOW_CALENDAR_TZ = "Europe/Moscow"

CB_TODAY = "exc:today"
CB_YESTERDAY = "exc:yesterday"
CB_PICK_DATE = "exc:pick_date"

# Невидимые символы в начале текста ломают Command() и F.text.startswith("/") —
# тогда срабатывает unknown_private_slash с return для /today → пользователь не получает ничего.
_LEADING_JUNK = "\ufeff\u200b\u200c\u200d\u2060"


def _strip_cmd_leading(s: str) -> str:
    t = (s or "").strip()
    while t and t[0] in _LEADING_JUNK:
        t = t[1:].lstrip()
    return t.strip()


def _parse_slash_command(message: Message) -> tuple[str | None, str | None]:
    """
    Разбор /команда@бот аргументы — без проверки @бота (в личке не критично).
    Возвращает (имя_команды lower, хвост аргументов или None).
    """
    raw = message.text or message.caption
    if not raw:
        return None, None
    text = _strip_cmd_leading(raw)
    if not text.startswith("/"):
        return None, None
    first, *rest = text.split(maxsplit=1)
    if len(first) < 2:
        return None, None
    body = first[1:]
    name = body.split("@", 1)[0].strip().casefold()
    if not name:
        return None, None
    args = rest[0].strip() if rest else None
    return name, args


class PlainCommand(Filter):
    """Устойчивый к BOM/ZWSP и к /cmd@anybot; не зависит от Command() и bot.me()."""

    __slots__ = ("names",)

    def __init__(self, *names: str):
        if not names:
            raise ValueError("plain command: need at least one name")
        self.names = frozenset(n.casefold() for n in names)

    async def __call__(self, message: Message) -> bool:
        cmd, _ = _parse_slash_command(message)
        return cmd is not None and cmd in self.names


def _callback_private_chat_ok(callback: CallbackQuery) -> bool:
    """Кнопки отчёта: в группах не обрабатываем; если message нет — считаем личку с ботом."""
    if callback.message is None or callback.message.chat is None:
        return True
    return callback.message.chat.type == "private"


def _private_text_looks_like_slash_command(message: Message) -> bool:
    raw = message.text or ""
    return bool(raw) and _strip_cmd_leading(raw).startswith("/")


class ExclusiveStates(StatesGroup):
    waiting_custom_date = State()


def default_tz() -> str:
    return os.environ.get("DEFAULT_TZ", "Europe/Moscow").strip() or "Europe/Moscow"


def report_nav_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Сегодня", callback_data=CB_TODAY)
    kb.button(text="Вчера", callback_data=CB_YESTERDAY)
    kb.button(text="Другая дата", callback_data=CB_PICK_DATE)
    kb.adjust(2, 1)
    return kb.as_markup()


def _validate_tz(tz_name: str) -> bool:
    try:
        ZoneInfo(tz_name)
    except Exception:
        return False
    return True


@asynccontextmanager
async def _typing_keepalive(bot, chat_id: int):
    """Пока идёт долгий HTTP-сбор, клиент Telegram видит «печатает…» (сбрасывается ~за 5 с)."""

    async def _loop() -> None:
        try:
            while True:
                await bot.send_chat_action(chat_id, ChatAction.TYPING)
                await asyncio.sleep(4.0)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.debug("send_chat_action failed", exc_info=True)

    task = asyncio.create_task(_loop())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


def _callback_chat_id(callback: CallbackQuery) -> int | None:
    if callback.message and callback.message.chat:
        return callback.message.chat.id
    if callback.from_user:
        return callback.from_user.id
    return None


async def _deliver_day_report(bot, chat_id: int, day: date, tz_name: str) -> None:
    try:
        async with create_client() as http:
            async with _typing_keepalive(bot, chat_id):
                items, results = await asyncio.wait_for(
                    collect_exclusives_for_day(day, tz_name, http),
                    timeout=_COLLECT_TIMEOUT_SEC,
                )
        failed = [r.source_id for r in results if r.error]
        chunks = build_telegram_chunks(day, tz_name, items, failed)
    except asyncio.TimeoutError:
        logger.error(
            "collect_exclusives_for_day timed out after %ss", _COLLECT_TIMEOUT_SEC
        )
        await bot.send_message(
            chat_id,
            "Сбор эксклюзивов занял слишком много времени (таймаут). "
            "Попробуйте ещё раз через минуту — возможна перегрузка сети или источников.",
            reply_markup=report_nav_keyboard(),
        )
        return
    except Exception:
        logger.exception("collect_exclusives_for_day failed")
        await bot.send_message(
            chat_id,
            "Сейчас не удалось получить эксклюзивы. Попробуйте чуть позже.",
            reply_markup=report_nav_keyboard(),
        )
        return

    last = len(chunks) - 1
    for i, part in enumerate(chunks):
        try:
            await bot.send_message(
                chat_id,
                part,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=report_nav_keyboard() if i == last else None,
            )
        except Exception:
            logger.exception("send_message failed for chunk %s/%s", i + 1, len(chunks))
            await bot.send_message(
                chat_id,
                "Часть отчёта не удалось отправить (ошибка Telegram). "
                "Попробуйте команду ещё раз.",
                reply_markup=report_nav_keyboard(),
            )
            return


async def _send_day_report(message: Message, day: date, tz_name: str) -> None:
    await _deliver_day_report(message.bot, message.chat.id, day, tz_name)


@router.message(PlainCommand("start"), F.chat.type == "private")
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Команды (только в личных сообщениях):\n"
        "/today — эксклюзивы за сегодня (календарный день по Москве)\n"
        "/yesterday — за вчера по Москве\n"
        "/day ГГГГ-ММ-ДД — за указанную дату (сутки по часовому поясу из DEFAULT_TZ)\n\n"
        "После отчёта можно нажать кнопки: Сегодня, Вчера, Другая дата.\n\n"
        f"DEFAULT_TZ для /day: {default_tz()}"
    )


@router.message(PlainCommand("today"), F.chat.type == "private")
async def cmd_today(message: Message, state: FSMContext) -> None:
    await state.clear()
    if not _validate_tz(MOSCOW_CALENDAR_TZ):
        await message.answer("Некорректный встроенный пояс Europe/Moscow.")
        return
    zi = ZoneInfo(MOSCOW_CALENDAR_TZ)
    d = datetime.now(zi).date()
    await _send_day_report(message, d, MOSCOW_CALENDAR_TZ)


@router.message(PlainCommand("yesterday"), F.chat.type == "private")
async def cmd_yesterday(message: Message, state: FSMContext) -> None:
    await state.clear()
    if not _validate_tz(MOSCOW_CALENDAR_TZ):
        await message.answer("Некорректный встроенный пояс Europe/Moscow.")
        return
    zi = ZoneInfo(MOSCOW_CALENDAR_TZ)
    d = datetime.now(zi).date() - timedelta(days=1)
    await _send_day_report(message, d, MOSCOW_CALENDAR_TZ)


@router.message(PlainCommand("day"), F.chat.type == "private")
async def cmd_day(message: Message, state: FSMContext) -> None:
    await state.clear()
    _, args = _parse_slash_command(message)
    if not args:
        await message.answer("Формат: /day 2026-03-29")
        return
    arg0 = args.strip().split()[0]
    try:
        d = date.fromisoformat(arg0)
    except ValueError:
        await message.answer(
            "Неверная дата. Укажите ГГГГ-ММ-ДД, например: /day 2026-03-29"
        )
        return
    tz_name = default_tz()
    if not _validate_tz(tz_name):
        await message.answer("Некорректный DEFAULT_TZ в настройках.")
        return
    await _send_day_report(message, d, tz_name)


@router.callback_query(
    F.data.in_({CB_TODAY, CB_YESTERDAY, CB_PICK_DATE}),
    F.func(_callback_private_chat_ok),
)
async def on_report_nav(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.data == CB_PICK_DATE:
        await state.set_state(ExclusiveStates.waiting_custom_date)
        await callback.answer()
        await callback.message.answer(
            "Укажите дату одним сообщением в формате ГГГГ-ММ-ДД, например 2026-03-29."
        )
        return

    await state.clear()
    if not _validate_tz(MOSCOW_CALENDAR_TZ):
        await callback.answer("Ошибка пояса Europe/Moscow", show_alert=True)
        return

    zi = ZoneInfo(MOSCOW_CALENDAR_TZ)
    if callback.data == CB_TODAY:
        d = datetime.now(zi).date()
    else:
        d = datetime.now(zi).date() - timedelta(days=1)

    chat_id = _callback_chat_id(callback)
    if chat_id is None:
        await callback.answer("Не удалось определить чат", show_alert=True)
        return
    await callback.answer()
    await _deliver_day_report(callback.bot, chat_id, d, MOSCOW_CALENDAR_TZ)


@router.message(ExclusiveStates.waiting_custom_date, F.chat.type == "private", F.text)
async def on_custom_date_text(message: Message, state: FSMContext) -> None:
    arg0 = message.text.strip().split()[0]
    try:
        d = date.fromisoformat(arg0)
    except ValueError:
        await message.answer(
            "Неверная дата. Нужен формат ГГГГ-ММ-ДД, например 2026-03-29."
        )
        return
    tz_name = default_tz()
    if not _validate_tz(tz_name):
        await message.answer("Некорректный DEFAULT_TZ в настройках.")
        await state.clear()
        return
    await state.clear()
    await _send_day_report(message, d, tz_name)


@router.message(ExclusiveStates.waiting_custom_date, F.chat.type == "private")
async def on_custom_date_non_text(message: Message) -> None:
    await message.answer("Отправьте дату текстом в формате ГГГГ-ММ-ДД.")


@router.message(
    F.chat.type != "private",
    PlainCommand("start", "today", "yesterday", "day"),
)
async def group_use_private_chat(message: Message) -> None:
    await message.reply(
        "Этот бот отвечает только в личном чате.\n"
        "Откройте профиль бота в Telegram и нажмите «Написать» или /start там."
    )


@router.message(
    F.chat.type == "private",
    F.text,
    F.func(_private_text_looks_like_slash_command),
)
async def unknown_private_slash(message: Message) -> None:
    """Неизвестные /команды — подсказка. Известные уже обработаны PlainCommand выше."""
    raw = message.text or ""
    if not _strip_cmd_leading(raw).startswith("/"):
        return
    cmd_name, _ = _parse_slash_command(message)
    if cmd_name in ("start", "today", "yesterday", "day"):
        # Должно было сработать PlainCommand — на всякий случай не молчим.
        logger.warning(
            "slash command %r reached unknown handler (PlainCommand miss)", cmd_name
        )
        await message.answer(
            "Команда распознана, но обработчик не сработал — отправьте ещё раз или /start."
        )
        return
    await message.answer(
        "Неизвестная команда. Отправьте /start — список команд и как получить подборку эксклюзивов."
    )
