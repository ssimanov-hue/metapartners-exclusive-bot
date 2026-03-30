from __future__ import annotations

from datetime import UTC, date, datetime, time

import httpx
from bs4 import BeautifulSoup

from bot.sources.dates_ru import MOSCOW, parse_vseprosport_stamp
from bot.sources.types import ExclusiveItem

LISTING_URL = "https://www.vseprosport.ru/lenta/"
_BASE = "https://www.vseprosport.ru"


async def fetch_exclusive_items(
    client: httpx.AsyncClient,
    target_day: date | None = None,
) -> list[ExclusiveItem]:
    """
    На /lenta/ блоки «Эксклюзив» в шапке — одинаковые на всех ?page=N (пагинация не расширяет список).
    Для «вчера/сегодня» в разметке карточек опорная дата — запрошенный календарный день (конец дня МСК).
    """
    from datetime import date as date_cls

    d = target_day or date_cls.today()
    now_moscow = datetime.combine(d, time(23, 59), tzinfo=MOSCOW)

    r = await client.get(LISTING_URL)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    items: list[ExclusiveItem] = []
    seen: set[str] = set()
    for badge in soup.select("div.exclusive"):
        text = badge.get_text(strip=True)
        if "ксклюз" not in text.lower() and "exclusive" not in text.lower():
            continue
        card = badge.find_parent("div", class_=lambda c: c and "featured__item" in c)
        if not card:
            continue
        link = card.select_one("a.position-absolute.full-area.text-hide")
        if not link or not link.has_attr("href"):
            link = card.select_one("a[href^='/lenta/']")
        if not link or not link.has_attr("href"):
            continue
        href = link["href"].strip()
        title = link.get_text(strip=True) or (link.get("title") or "").strip()
        if not title:
            p = card.select_one("p.card-title")
            if p:
                title = p.get_text(strip=True)
        if not title:
            continue
        url = href if href.startswith("http") else _BASE + href.split("#", 1)[0]
        if url in seen:
            continue
        dt = None
        for span in card.find_all("span"):
            txt = span.get_text(" ", strip=True)
            if not txt or txt.casefold() == "эксклюзив":
                continue
            dt = parse_vseprosport_stamp(txt, now_moscow)
            if dt is not None:
                break
        if dt is None:
            dt = parse_vseprosport_stamp(
                card.get_text(" ", strip=True).replace("\xa0", " "), now_moscow
            )
        if dt is None:
            continue
        seen.add(url)
        items.append(
            ExclusiveItem(url=url, title=title, published_at=dt.astimezone(UTC))
        )
    items.sort(key=lambda x: x.published_at, reverse=True)
    return items
