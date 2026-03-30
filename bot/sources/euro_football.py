from __future__ import annotations

from datetime import UTC, date

import httpx
from bs4 import BeautifulSoup

from bot.sources.dates_ru import parse_euro_football_date_line
from bot.sources.types import ExclusiveItem

LISTING_URL = "https://www.euro-football.ru/article?indicator=14"
_BASE = "https://www.euro-football.ru"


async def fetch_exclusive_items(
    client: httpx.AsyncClient,
    target_day: date | None = None,
) -> list[ExclusiveItem]:
    """
    Рубрика «эксклюзив» (indicator=14). Год в строке даты карточки — из target_day для /day ….
    """
    from datetime import date as date_cls

    r = await client.get(LISTING_URL)
    r.raise_for_status()
    year = (target_day or date_cls.today()).year
    soup = BeautifulSoup(r.text, "html.parser")
    items: list[ExclusiveItem] = []
    seen: set[str] = set()
    for block in soup.select("div.additional-content-item"):
        title_a = block.select_one("a.additional-content-item__content-title")
        if not title_a or not title_a.has_attr("href"):
            continue
        href = title_a["href"].strip()
        title = title_a.get_text(strip=True)
        if not href or not title:
            continue
        url = href if href.startswith("http") else _BASE + href.split("#", 1)[0]
        if url in seen:
            continue
        date_el = block.select_one("div.additional-content-item__content-date")
        if not date_el:
            continue
        raw_date = date_el.get_text(" ", strip=True)
        dt = parse_euro_football_date_line(raw_date, year)
        if dt is None:
            continue
        seen.add(url)
        items.append(
            ExclusiveItem(url=url, title=title, published_at=dt.astimezone(UTC))
        )
    return items
