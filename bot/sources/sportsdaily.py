from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import date, datetime
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from bot.sources.dates_ru import parse_iso_z, parse_sportsdaily_stamp
from bot.sources.types import ExclusiveItem

logger = logging.getLogger(__name__)

LISTING_URL = "https://www.sportsdaily.ru/eksklyuziv/"
SITEMAP_INDEX = "https://www.sportsdaily.ru/sitemap.xml"
_BASE = "https://www.sportsdaily.ru"

_NEWS_SITEMAP_RE = re.compile(
    r"<loc>(https://www\.sportsdaily\.ru/sitemap-news-\d+\.xml)</loc>"
)
_URL_BLOCK_RE = re.compile(r"<url>(.*?)</url>", re.DOTALL)
_LOC_RE = re.compile(r"<loc>([^<]+)</loc>")
_LASTMOD_RE = re.compile(r"<lastmod>([^<]+)</lastmod>")

_STAMP_IN_SPAN = re.compile(
    r"\d{1,2}:\d{2}\s*[·•]\s*\d{2}\.\d{2}\.\d{4}",
)

_CONCURRENCY = 6
_LISTING_RETRIES = 3


async def _get_retry(client: httpx.AsyncClient, url: str) -> httpx.Response:
    """Повтор при обрыве TLS/сокета (часто на длинной выдаче)."""
    last: BaseException | None = None
    for attempt in range(_LISTING_RETRIES):
        try:
            r = await client.get(url)
            r.raise_for_status()
            return r
        except (httpx.ReadError, httpx.RemoteProtocolError, httpx.ConnectTimeout) as e:
            last = e
            await asyncio.sleep(0.5 * (attempt + 1))
    assert last is not None
    raise last


def _lastmod_calendar_date(s: str) -> date | None:
    try:
        return datetime.fromisoformat(s.strip().replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _has_exclusive_badge(container: BeautifulSoup) -> bool:
    for span in container.find_all("span"):
        t = span.get_text(strip=True).casefold()
        if t == "эксклюзив":
            return True
    return False


def _find_title_link(container: BeautifulSoup) -> tuple[str, str] | None:
    for a in container.find_all("a", href=True):
        href = a["href"]
        if href.startswith("/articles/") or href.startswith("/news/"):
            title = a.get_text(strip=True)
            if title and href != "/undefined":
                return href, title
    return None


def _items_from_eksklyuziv_listing(html: str) -> list[ExclusiveItem]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[ExclusiveItem] = []
    seen: set[str] = set()
    for div in soup.find_all(True, attrs={"class": True}):
        classes = div.get("class") or []
        if not any("articleCard_articleCardTextContainer" in c for c in classes):
            continue
        if not _has_exclusive_badge(div):
            continue
        pair = _find_title_link(div)
        if not pair:
            continue
        href, title = pair
        url = _BASE + href.split("#", 1)[0]
        if url in seen:
            continue
        stamp = None
        for span in div.find_all("span"):
            txt = span.get_text(" ", strip=True)
            if _STAMP_IN_SPAN.search(txt):
                stamp = txt
                break
        if not stamp:
            continue
        dt = parse_sportsdaily_stamp(stamp)
        if dt is None:
            continue
        seen.add(url)
        items.append(ExclusiveItem(url=url, title=title, published_at=dt))
    return items


async def _news_urls_for_calendar_day(
    client: httpx.AsyncClient, day: date
) -> list[str]:
    """URL /news/... из sitemap-news-*.xml с lastmod в календарный день day."""
    try:
        ix = await client.get(SITEMAP_INDEX)
        ix.raise_for_status()
    except Exception:
        logger.exception("Sportsdaily sitemap index failed")
        return []

    day_str = day.isoformat()
    out: list[str] = []
    seen: set[str] = set()

    for sm_url in _NEWS_SITEMAP_RE.findall(ix.text):
        try:
            r = await client.get(sm_url)
            r.raise_for_status()
        except Exception:
            logger.debug("Sportsdaily sitemap chunk failed: %s", sm_url, exc_info=True)
            continue
        if day_str not in r.text:
            continue
        for block in _URL_BLOCK_RE.findall(r.text):
            lm_m = _LASTMOD_RE.search(block)
            loc_m = _LOC_RE.search(block)
            if not lm_m or not loc_m:
                continue
            if _lastmod_calendar_date(lm_m.group(1)) != day:
                continue
            loc = loc_m.group(1).strip().split("#", 1)[0]
            path = urlparse(loc).path
            if not path.startswith("/news/"):
                continue
            if loc not in seen:
                seen.add(loc)
                out.append(loc)
    return out


def _article_tags_exclusive(soup: BeautifulSoup) -> bool:
    """Тег материала «Эксклюзивы» → /eksklyuziv/ (не пункт меню)."""
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if href not in ("/eksklyuziv/", f"{_BASE}/eksklyuziv/", f"{_BASE}/eksklyuziv"):
            continue
        classes = [str(c) for c in (a.get("class") or [])]
        blob = " ".join(classes)
        if "tagItem" not in blob:
            continue
        if "эксклюзив" in a.get_text(strip=True).casefold():
            return True
    return False


def _ld_json_news_article(html: str) -> tuple[str, datetime] | None:
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", type="application/ld+json"):
        raw = (script.string or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict) or data.get("@type") != "NewsArticle":
            continue
        title = (data.get("headline") or "").strip()
        dp = (data.get("datePublished") or "").strip()
        if not title or not dp:
            continue
        dt = parse_iso_z(dp)
        if dt is None:
            continue
        return title, dt
    return None


async def _fetch_news_page_exclusive(
    client: httpx.AsyncClient, url: str
) -> ExclusiveItem | None:
    try:
        r = await client.get(url)
        r.raise_for_status()
    except Exception:
        logger.debug("Sportsdaily article fetch failed: %s", url, exc_info=True)
        return None
    html = r.text
    soup = BeautifulSoup(html, "html.parser")
    if not _article_tags_exclusive(soup):
        return None
    parsed = _ld_json_news_article(html)
    if not parsed:
        return None
    title, published_at = parsed
    clean = url.split("#", 1)[0]
    return ExclusiveItem(url=clean, title=title, published_at=published_at)


async def fetch_exclusive_items(
    client: httpx.AsyncClient,
    target_day: date | None = None,
) -> list[ExclusiveItem]:
    """
    1) Лента /eksklyuziv/
    2) Sitemap news: все /news/... с lastmod = target_day и тегом «Эксклюзивы» на странице
       (интервью в /news/ часто не попадают в HTML ленты «Эксклюзивы»).
    """
    from datetime import date as date_cls

    day = target_day or date_cls.today()
    by_url: dict[str, ExclusiveItem] = {}

    try:
        lr = await _get_retry(client, LISTING_URL)
        for it in _items_from_eksklyuziv_listing(lr.text):
            by_url[it.url] = it
    except Exception:
        logger.exception("Sportsdaily /eksklyuziv/ listing failed")

    extra_urls = await _news_urls_for_calendar_day(client, day)
    sem = asyncio.Semaphore(_CONCURRENCY)

    async def bounded(u: str) -> ExclusiveItem | None:
        if u in by_url:
            return None
        async with sem:
            return await _fetch_news_page_exclusive(client, u)

    found = await asyncio.gather(*(bounded(u) for u in extra_urls))
    for it in found:
        if it is not None:
            by_url[it.url] = it

    out = list(by_url.values())
    out.sort(key=lambda x: x.published_at, reverse=True)
    return out
