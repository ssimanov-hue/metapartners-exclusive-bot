from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, date, datetime, time
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from bot.sources.dates_ru import MOSCOW
from bot.sources.types import ExclusiveItem

logger = logging.getLogger(__name__)

RT_BASE = "https://russian.rt.com"
# Архив ленты спорта за календарный день (как на сайте RT)
SPORT_NEWS_DAY_URL = RT_BASE + "/sport/news/{:%Y-%m-%d}/"

_RE_DATETIME_ATTR = re.compile(
    r"^\s*(\d{4})-(\d{2})-(\d{2})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?\s*$"
)

_EXCLUSIVE_CLASS_SNIPPET = "card__informal_exclusive"
_EXCLUSIVE_TEXT = "эксклюзив rt"

_CONCURRENCY = 6


def _listing_sport_article_urls(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[str] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = str(a["href"]).strip()
        if "/sport/article/" not in href:
            continue
        if href.startswith("/"):
            full = urljoin(RT_BASE, href.split("#", 1)[0])
        elif href.startswith("http"):
            full = href.split("#", 1)[0]
        else:
            continue
        host = urlparse(full).netloc.lower()
        if host.endswith("rt.com") and full not in seen:
            seen.add(full)
            out.append(full)
    return out


def _parse_article_published_utc(html: str) -> datetime | None:
    """Первый <time datetime>; без TZ считаем Europe/Moscow (как в вёрстке RT)."""
    soup = BeautifulSoup(html, "html.parser")
    for t in soup.find_all("time"):
        raw = (t.get("datetime") or "").strip()
        if not raw:
            continue
        m = _RE_DATETIME_ATTR.match(raw)
        if not m:
            continue
        y, mo, d, hh, mi = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(5))
        sec = int(m.group(6) or 0)
        try:
            local = datetime(y, mo, d, hh, mi, sec, tzinfo=MOSCOW)
            return local.astimezone(UTC)
        except ValueError:
            continue
    return None


def _align_published_to_listing_day(parsed_utc: datetime, listing_day: date) -> datetime:
    """
    Статьи в архиве /sport/news/YYYY-MM-DD/ иногда имеют <time> на следующий день по МСК;
    для отчёта за выбранные сутки относим такие материалы к дню архива (полдень МСК).
    """
    m_date = parsed_utc.astimezone(MOSCOW).date()
    if m_date == listing_day:
        return parsed_utc
    noon = datetime.combine(listing_day, time(12, 0), tzinfo=MOSCOW)
    return noon.astimezone(UTC)


def _article_is_rt_exclusive(html: str) -> bool:
    low = html.casefold()
    if _EXCLUSIVE_CLASS_SNIPPET in low:
        return True
    return _EXCLUSIVE_TEXT in low.replace("\xa0", " ").casefold()


def _article_title(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        return str(og["content"]).strip()
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)
    return None


async def _fetch_one_article(
    client: httpx.AsyncClient, url: str, listing_day: date
) -> ExclusiveItem | None:
    try:
        r = await client.get(url)
        r.raise_for_status()
    except Exception:
        logger.debug("RT article fetch failed: %s", url, exc_info=True)
        return None
    html = r.text
    if not _article_is_rt_exclusive(html):
        return None
    dt = _parse_article_published_utc(html)
    if dt is None:
        return None
    dt = _align_published_to_listing_day(dt, listing_day)
    title = _article_title(html)
    if not title:
        return None
    return ExclusiveItem(url=url.split("#", 1)[0], title=title, published_at=dt)


async def fetch_exclusive_items(
    client: httpx.AsyncClient,
    target_day: date | None = None,
) -> list[ExclusiveItem]:
    """
    Материалы «Эксклюзив RT» из архива /sport/news/ за target_day.
    Англоязычный RSS не содержит нужных маркеров — используем русскую вёрстку.
    """
    from datetime import date as date_cls

    day = target_day or date_cls.today()
    listing_url = SPORT_NEWS_DAY_URL.format(day)
    try:
        lr = await client.get(listing_url)
        lr.raise_for_status()
    except Exception:
        logger.exception("RT listing fetch failed: %s", listing_url)
        return []

    urls = _listing_sport_article_urls(lr.text)
    if not urls:
        return []

    sem = asyncio.Semaphore(_CONCURRENCY)

    async def bounded(u: str) -> ExclusiveItem | None:
        async with sem:
            return await _fetch_one_article(client, u, day)

    results = await asyncio.gather(*(bounded(u) for u in urls))
    items = [x for x in results if x is not None]
    items.sort(key=lambda x: x.published_at, reverse=True)
    return items
