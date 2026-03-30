from __future__ import annotations

import re
from datetime import UTC, date, datetime

import httpx
from bs4 import BeautifulSoup

from bot.sources.dates_ru import MOSCOW, parse_ru_day_month_at_time
from bot.sources.types import ExclusiveItem

LISTING_URL = "https://odds.ru/news/exclusive/"
_BASE = "https://odds.ru"
_MAX_PAGES = 30

_RE_DATE_LINE = re.compile(
    r"(\d{1,2})\s+([а-яА-ЯёЁ]+)\s+в\s+(\d{1,2}):(\d{2})",
)


def _parse_date_from_li(li: BeautifulSoup, year: int) -> datetime | None:
    text = li.get_text(" ", strip=True)
    m = _RE_DATE_LINE.search(text)
    if not m:
        return None
    fake = f"{m.group(1)} {m.group(2)} в {m.group(3)}:{m.group(4)}"
    return parse_ru_day_month_at_time(fake, year)


def _items_from_listing_html(html: str, year: int) -> list[ExclusiveItem]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[ExclusiveItem] = []
    seen: set[str] = set()
    for a in soup.select('a[href^="/news/exclusive/"]'):
        href = a.get("href") or ""
        if not href.startswith("/news/exclusive/"):
            continue
        url = _BASE + href.split("?", 1)[0].rstrip("/") + "/"
        if url in seen:
            continue
        title = (a.get("title") or a.get_text(strip=True) or "").strip()
        if not title:
            continue
        li = a.find_parent("li")
        if not li:
            continue
        dt = _parse_date_from_li(li, year)
        if dt is None:
            continue
        seen.add(url)
        items.append(
            ExclusiveItem(
                url=url,
                title=title,
                published_at=dt.astimezone(UTC),
            )
        )
    return items


async def fetch_exclusive_items(
    client: httpx.AsyncClient,
    target_day: date | None = None,
) -> list[ExclusiveItem]:
    """
    Лента /news/exclusive/ с пагинацией ?page=N.
    Год в дате «29 марта в …» берётся из target_day (для /day …), иначе текущий год по МСК.
    """
    from datetime import date as date_cls

    ref_day = target_day or datetime.now(MOSCOW).date()
    year = ref_day.year

    seen: set[str] = set()
    merged: list[ExclusiveItem] = []

    page = 1
    while page <= _MAX_PAGES:
        url = LISTING_URL if page == 1 else f"{LISTING_URL}?page={page}"
        r = await client.get(url)
        r.raise_for_status()
        batch = _items_from_listing_html(r.text, year)
        added = 0
        for it in batch:
            if it.url not in seen:
                seen.add(it.url)
                merged.append(it)
                added += 1
        if added == 0:
            break
        page += 1

    merged.sort(key=lambda x: x.published_at, reverse=True)
    return merged
