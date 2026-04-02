from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, date, datetime, time
from urllib.parse import urljoin, urlparse

import feedparser
import httpx
from bs4 import BeautifulSoup

from bot.services.filters import normalize_url
from bot.sources.dates_ru import MOSCOW
from bot.sources.types import ExclusiveItem

logger = logging.getLogger(__name__)

RT_BASE = "https://russian.rt.com"
SPORT_NEWS_DAY_URL = RT_BASE + "/sport/news/{:%Y-%m-%d}/"

_RE_BAD_ARCHIVE_PATH = re.compile(r"^/article/\d{4}$")
_RE_HREF_SPORT_NEWS_ITEM = re.compile(r"/sport/news/\d+-.+")

_RE_DATETIME_ATTR = re.compile(
    r"^\s*(\d{4})-(\d{2})-(\d{2})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?\s*$"
)

_EXCLUSIVE_CLASS_SNIPPET = "card__informal_exclusive"
_EXCLUSIVE_TEXT = "эксклюзив rt"

# Типичные формулировки пересказа цитат с других СМИ (короткие /sport/news/).
_AGGREGATION_CUES: tuple[str, ...] = (
    "приводит его слова",
    "приводит её слова",
    "приводит ее слова",
    "приводит их слова",
    "приводит слова",
    "передаёт слова",
    "передает слова",
    "со слов",
)

_CONCURRENCY = 6
_SPORT_HUB_MAX_PAGES = 8
_SPORT_NEWS_LIST_MAX_PAGES = 12
RT_RSS_URL = RT_BASE + "/rss"


def _candidate_rt_sport_item_url(href: str) -> str | None:
    """
    Нормализует ссылку на материал спорта RT: /sport/article/... или
    /sport/news/<id>-<slug> (не архив за день /sport/news/ГГГГ-ММ-ДД).
    """
    raw = str(href).strip()
    if not raw:
        return None
    path_only = raw.split("#", 1)[0]
    if path_only.startswith("/"):
        full = urljoin(RT_BASE, path_only)
    elif path_only.startswith("http"):
        full = path_only
    else:
        return None
    full = full.split("#", 1)[0]
    parsed = urlparse(full)
    if not parsed.netloc.lower().endswith("rt.com"):
        return None
    path = (parsed.path or "").rstrip("/")
    if "/sport/article/" in path:
        return full
    if not path.startswith("/sport/news/"):
        return None
    tail = path[len("/sport/news/") :].lstrip("/")
    if not tail or "/" in tail:
        return None
    if re.match(r"^\d{4}-\d{2}-\d{2}$", tail):
        return None
    if re.match(r"^\d+-.+", tail):
        return full
    return None


def _listing_sport_article_urls(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[str] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        full = _candidate_rt_sport_item_url(str(a["href"]))
        if full is None or full in seen:
            continue
        seen.add(full)
        out.append(full)
    return out


def _listing_sport_news_exclusive_feed_urls(html: str) -> list[str]:
    """
    Только карточки ленты https://russian.rt.com/sport/news с зелёной пометкой «Эксклюзив RT»
    (span.card__informal_exclusive внутри listing__card_all-news / listing__card_short-news).
    """
    soup = BeautifulSoup(html, "html.parser")
    out: list[str] = []
    seen: set[str] = set()
    for sp in soup.select("span.card__informal_exclusive"):
        label = sp.get_text().replace("\xa0", " ").strip().casefold()
        if "эксклюзив" not in label or "rt" not in label:
            continue
        card = None
        x = sp.parent
        for _ in range(15):
            if x is None:
                break
            cls = x.get("class") or []
            if x.name == "div" and "listing__card" in cls:
                card = x
                break
            x = x.parent
        if card is None:
            continue
        cstr = " ".join(card.get("class") or [])
        if (
            "listing__card_all-news" not in cstr
            and "listing__card_short-news" not in cstr
        ):
            continue
        for a in card.find_all("a", href=True):
            href = str(a["href"]).strip().split("#", 1)[0]
            if not _RE_HREF_SPORT_NEWS_ITEM.search(href):
                continue
            full = urljoin(RT_BASE, href)
            if full not in seen:
                seen.add(full)
                out.append(full)
            break
    return out


def _parse_article_published_utc(html: str) -> datetime | None:
    soup = BeautifulSoup(html, "html.parser")
    for t in soup.find_all("time"):
        raw = (t.get("datetime") or "").strip()
        if not raw:
            continue
        m = _RE_DATETIME_ATTR.match(raw)
        if m:
            y, mo, d, hh, mi = (
                int(m.group(1)),
                int(m.group(2)),
                int(m.group(3)),
                int(m.group(4)),
                int(m.group(5)),
            )
            sec = int(m.group(6) or 0)
            try:
                local = datetime(y, mo, d, hh, mi, sec, tzinfo=MOSCOW)
                return local.astimezone(UTC)
            except ValueError:
                continue
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=MOSCOW)
        try:
            return dt.astimezone(UTC)
        except (ValueError, OSError):
            continue
    return None


def _align_published_to_listing_day(parsed_utc: datetime, listing_day: date) -> datetime:
    m_date = parsed_utc.astimezone(MOSCOW).date()
    if m_date == listing_day:
        return parsed_utc
    noon = datetime.combine(listing_day, time(12, 0), tzinfo=MOSCOW)
    return noon.astimezone(UTC)


def _aggregation_in_text(text: str) -> bool:
    t = text.replace("\xa0", " ").casefold()
    return any(cue in t for cue in _AGGREGATION_CUES)


def _rt_article_core_fragments(main) -> tuple[str, str]:
    """Текст и HTML только заголовка, лида и основного текста (без тегов, шаринга, сайдбаров)."""
    text_parts: list[str] = []
    html_parts: list[str] = []
    for sel in (
        "div.article__heading",
        "div.article__summary",
        "div.article__text",
    ):
        el = main.select_one(sel)
        if el is None:
            continue
        text_parts.append(el.get_text().replace("\xa0", " "))
        html_parts.append(str(el))
    return " ".join(text_parts), " ".join(html_parts)


def _article_is_rt_exclusive(html: str, *, article_url: str = "") -> bool:
    """
    RT помечает эксклюзив темой в блоке тегов статьи (article__tags-trends) — это совпадает
    с редакционным смыслом и не цепляет сайдбар «других» эксклюзивов на странице.

    Если блока тегов нет (старый шаблон) — смотрим только heading/summary/text, плюс
    для /sport/news/ отсекаем явные пересказы с цитатами других СМИ.
    """
    soup = BeautifulSoup(html, "html.parser")
    main = soup.select_one("div.article.article_article-page") or soup.select_one(
        "div.article"
    )
    if main is None:
        return False

    tags = main.select_one(".article__tags-trends")
    if tags is not None:
        tag_text = tags.get_text().replace("\xa0", " ").casefold()
        return _EXCLUSIVE_TEXT in tag_text

    core_text, core_html = _rt_article_core_fragments(main)
    if not core_text.strip():
        return False

    low_html = core_html.casefold()
    low_text = core_text.casefold()
    if _EXCLUSIVE_CLASS_SNIPPET in low_html:
        exclusive = True
    else:
        exclusive = _EXCLUSIVE_TEXT in low_text

    if not exclusive:
        return False

    path = urlparse(article_url).path
    if "/sport/news/" in path:
        body_el = main.select_one("div.article__text")
        body_txt = body_el.get_text().replace("\xa0", " ") if body_el else core_text
        if _aggregation_in_text(body_txt):
            return False

    return True


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


async def _gather_sport_hub_sport_article_urls(client: httpx.AsyncClient) -> list[str]:
    """С главной /sport и ?page=N — только ссылки /sport/article/ (уникальные)."""
    ordered: list[str] = []
    seen: set[str] = set()
    for page in range(1, _SPORT_HUB_MAX_PAGES + 1):
        url = RT_BASE + "/sport" if page == 1 else f"{RT_BASE}/sport?page={page}"
        try:
            r = await client.get(url)
            r.raise_for_status()
        except Exception:
            logger.debug("RT sport hub page failed: %s", url, exc_info=True)
            break
        chunk = _listing_sport_article_urls(r.text)
        added_any = False
        for u in chunk:
            if u not in seen:
                seen.add(u)
                ordered.append(u)
                added_any = True
        if not added_any:
            break
    return ordered


async def _gather_sport_news_exclusive_feed_urls(client: httpx.AsyncClient) -> list[str]:
    """
    Эксклюзивы только с ленты https://russian.rt.com/sport/news — карточки с пометкой «Эксклюзив RT»
    (зелёный бейдж в вёрстке: span.card__informal_exclusive).
    """
    ordered: list[str] = []
    seen: set[str] = set()
    for page in range(1, _SPORT_NEWS_LIST_MAX_PAGES + 1):
        url = RT_BASE + "/sport/news" if page == 1 else f"{RT_BASE}/sport/news?page={page}"
        try:
            r = await client.get(url)
            r.raise_for_status()
        except Exception:
            logger.debug("RT /sport/news exclusive feed failed: %s", url, exc_info=True)
            break
        chunk = _listing_sport_news_exclusive_feed_urls(r.text)
        added_any = False
        for u in chunk:
            if u not in seen:
                seen.add(u)
                ordered.append(u)
                added_any = True
        if not added_any and page > 1:
            break
    return ordered


async def _gather_rss_sport_item_urls(client: httpx.AsyncClient) -> list[str]:
    """
    russian.rt.com/rss — подмешиваем только длинные /sport/article/ (интервью),
    короткие эксклюзивы /sport/news/ берём только с ленты /sport/news с зелёной пометкой.
    """
    try:
        r = await client.get(RT_RSS_URL)
        r.raise_for_status()
    except Exception:
        logger.debug("RT RSS fetch failed: %s", RT_RSS_URL, exc_info=True)
        return []

    parsed = feedparser.parse(r.text)
    out: list[str] = []
    seen_keys: set[str] = set()
    for entry in getattr(parsed, "entries", []) or []:
        link = (entry.get("link") or "").strip()
        if not link:
            continue
        link = link.split("#", 1)[0]
        full = _candidate_rt_sport_item_url(link)
        if full is None:
            continue
        if "/sport/article/" not in urlparse(full).path:
            continue
        key = normalize_url(full)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        out.append(full)
    return out


async def _fetch_one_article(
    client: httpx.AsyncClient,
    url: str,
    listing_day: date,
    *,
    align_to_listing_day: bool,
    trusted_listing_exclusive: bool = False,
) -> ExclusiveItem | None:
    try:
        r = await client.get(url)
        r.raise_for_status()
    except Exception:
        logger.debug("RT article fetch failed: %s", url, exc_info=True)
        return None
    html = r.text
    if not trusted_listing_exclusive and not _article_is_rt_exclusive(
        html, article_url=url
    ):
        return None
    dt = _parse_article_published_utc(html)
    if dt is None:
        return None
    if align_to_listing_day:
        dt = _align_published_to_listing_day(dt, listing_day)
    else:
        if dt.astimezone(MOSCOW).date() != listing_day:
            return None
    title = _article_title(html)
    if not title:
        return None
    return ExclusiveItem(url=url.split("#", 1)[0], title=title, published_at=dt)


async def fetch_exclusive_items(
    client: httpx.AsyncClient,
    target_day: date | None = None,
) -> list[ExclusiveItem]:
    """
    Эксклюзивы RT:
    — короткие: только с ленты https://russian.rt.com/sport/news (карточки с «Эксклюзив RT»);
    — длинные /sport/article/: архив дня, хаб /sport и RSS (с проверкой страницы материала).
    """
    from datetime import date as date_cls

    day = target_day or date_cls.today()
    listing_url = SPORT_NEWS_DAY_URL.format(day)
    align = True
    try:
        lr = await client.get(listing_url)
        lr.raise_for_status()
    except Exception:
        logger.exception("RT listing fetch failed: %s", listing_url)
        return []

    final_path = urlparse(str(lr.url)).path
    if _RE_BAD_ARCHIVE_PATH.match(final_path):
        logger.info(
            "RT day archive redirects to %s — using /sport hub fallback",
            final_path,
        )
        urls = await _gather_sport_hub_sport_article_urls(client)
        align = False
    else:
        urls = _listing_sport_article_urls(lr.text)

    primary = list(urls)
    primary_set = set(primary)
    feed_exclusive = await _gather_sport_news_exclusive_feed_urls(client)
    rss_articles = await _gather_rss_sport_item_urls(client)
    extra: list[tuple[str, bool]] = []
    seen_extra: set[str] = set()
    for u in feed_exclusive:
        if u in primary_set or u in seen_extra:
            continue
        seen_extra.add(u)
        extra.append((u, True))
    for u in rss_articles:
        if u in primary_set or u in seen_extra:
            continue
        seen_extra.add(u)
        extra.append((u, False))

    sem = asyncio.Semaphore(_CONCURRENCY)

    async def bounded(
        u: str, *, align_day: bool, trusted_feed: bool
    ) -> ExclusiveItem | None:
        async with sem:
            return await _fetch_one_article(
                client,
                u,
                day,
                align_to_listing_day=align_day,
                trusted_listing_exclusive=trusted_feed,
            )

    tasks = [bounded(u, align_day=align, trusted_feed=False) for u in primary]
    tasks.extend(
        bounded(u, align_day=False, trusted_feed=trusted) for u, trusted in extra
    )
    results = await asyncio.gather(*tasks)
    items = [x for x in results if x is not None]
    items.sort(key=lambda x: x.published_at, reverse=True)
    return items
