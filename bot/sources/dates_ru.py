from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from dateutil import parser as date_parser

MOSCOW = ZoneInfo("Europe/Moscow")

_RU_MONTHS = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
    "январь": 1,
    "февраль": 2,
    "март": 3,
    "апрель": 4,
    "июнь": 6,
    "июль": 7,
    "август": 8,
    "сентябрь": 9,
    "октябрь": 10,
    "ноябрь": 11,
    "декабрь": 12,
}

# "29 марта в 14:07" / "29 Марта в 17:15"
_RE_DAY_MONTH_TIME = re.compile(
    r"(\d{1,2})\s+([а-яА-ЯёЁ]+)\s+в\s+(\d{1,2}):(\d{2})",
    re.IGNORECASE,
)

# sportsdaily: "10:57 · 29.03.2026" (средняя точка или bullet)
_RE_TIME_DOT_DATE = re.compile(
    r"(\d{1,2}):(\d{2})\s*[·•]\s*(\d{2})\.(\d{2})\.(\d{4})",
)


def to_utc_moscow(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=MOSCOW)
    return dt.astimezone(UTC)


def parse_iso_z(value: str) -> datetime | None:
    value = value.strip()
    if not value:
        return None
    try:
        dt = date_parser.isoparse(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except (ValueError, TypeError):
        return None


def parse_ru_day_month_at_time(text: str, default_year: int) -> datetime | None:
    m = _RE_DAY_MONTH_TIME.search(text.replace("\xa0", " "))
    if not m:
        return None
    day_s, mon_s, hh, mm = m.group(1), m.group(2).lower(), m.group(3), m.group(4)
    month = _RU_MONTHS.get(mon_s.lower())
    if not month:
        return None
    try:
        dt = datetime(
            default_year, month, int(day_s), int(hh), int(mm), 0, tzinfo=MOSCOW
        )
        return dt.astimezone(UTC)
    except ValueError:
        return None


def parse_sportsdaily_stamp(text: str) -> datetime | None:
    m = _RE_TIME_DOT_DATE.search(text.replace("\xa0", " "))
    if not m:
        return None
    hh, mi, d, mo, y = m.groups()
    try:
        dt = datetime(int(y), int(mo), int(d), int(hh), int(mi), 0, tzinfo=MOSCOW)
        return dt.astimezone(UTC)
    except ValueError:
        return None


def parse_euro_football_date_line(text: str, default_year: int) -> datetime | None:
    cleaned = re.sub(r"\s+", " ", text.strip())
    return parse_ru_day_month_at_time(cleaned, default_year)


_RE_TIME_AFTER_V = re.compile(r"в\s+(\d{1,2}):(\d{2})", re.IGNORECASE)


def parse_vseprosport_stamp(text: str, now_moscow: datetime) -> datetime | None:
    """Parse card stamp like «Вчера в 14:44» or «29 марта в 14:44»."""
    raw = text.replace("\xa0", " ").strip()
    low = raw.casefold()
    today = now_moscow.date()
    if low.startswith("сегодня"):
        day = today
    elif low.startswith("вчера"):
        day = today - timedelta(days=1)
    elif low.startswith("позавчера"):
        day = today - timedelta(days=2)
    else:
        return parse_ru_day_month_at_time(raw, now_moscow.year)
    mt = _RE_TIME_AFTER_V.search(raw)
    if not mt:
        return None
    hh, mm = int(mt.group(1)), int(mt.group(2))
    try:
        dt = datetime(day.year, day.month, day.day, hh, mm, 0, tzinfo=MOSCOW)
        return dt.astimezone(UTC)
    except ValueError:
        return None
