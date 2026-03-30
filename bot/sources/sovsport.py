from __future__ import annotations

import json
import re
from typing import Any

import httpx

from bot.sources.dates_ru import parse_iso_z
from bot.sources.types import ExclusiveItem

LISTING_FIRST = "https://www.sovsport.ru/exclusive"
_BASE = "https://www.sovsport.ru"
_MAX_PAGES = 30


def _next_data_json(html: str) -> dict[str, Any] | None:
    m = re.search(
        r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
        html,
        re.DOTALL,
    )
    if not m:
        return None
    return json.loads(m.group(1))


def _article_url(item: dict[str, Any]) -> str:
    slug = (item.get("url") or "").strip().strip("/")
    sport = (item.get("sportCategory") or {}).get("typeId") or "football"
    ctype = (item.get("contentType") or {}).get("name") or "news"
    if ctype == "articles":
        return f"{_BASE}/{sport}/articles/{slug}"
    return f"{_BASE}/{sport}/news/{slug}"


def _collect_blocks(page_props: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    articles = page_props.get("articles") or {}
    news = page_props.get("news") or {}
    for container in (articles, news):
        if not isinstance(container, dict):
            continue
        for key, val in container.items():
            if isinstance(val, list):
                out.extend([x for x in val if isinstance(x, dict)])
    return out


def _items_from_page_html(html: str) -> list[ExclusiveItem]:
    data = _next_data_json(html)
    if not data:
        return []
    props = (data.get("props") or {}).get("pageProps") or {}
    items: list[ExclusiveItem] = []
    for raw in _collect_blocks(props):
        slug = raw.get("url")
        title = (raw.get("title") or "").strip()
        pub = raw.get("publicPublishedAt")
        if not slug or not title or not pub:
            continue
        url = _article_url(raw)
        dt = parse_iso_z(str(pub))
        if dt is None:
            continue
        items.append(ExclusiveItem(url=url, title=title, published_at=dt))
    return items


async def fetch_exclusive_items(client: httpx.AsyncClient) -> list[ExclusiveItem]:
    """
    Рубрика /exclusive на Next.js: первая страница + /exclusive/N/, пока появляются новые URL.
    (Только /exclusive без номера даёт тот же контент, что ?page=2 — номерные URL — источник страниц.)
    """
    seen: set[str] = set()
    merged: list[ExclusiveItem] = []

    r = await client.get(LISTING_FIRST)
    r.raise_for_status()
    for it in _items_from_page_html(r.text):
        if it.url not in seen:
            seen.add(it.url)
            merged.append(it)

    for page in range(2, _MAX_PAGES + 1):
        url = f"{_BASE}/exclusive/{page}/"
        resp = await client.get(url)
        if resp.status_code == 404:
            break
        resp.raise_for_status()
        batch = _items_from_page_html(resp.text)
        added = 0
        for it in batch:
            if it.url not in seen:
                seen.add(it.url)
                merged.append(it)
                added += 1
        if added == 0:
            break

    merged.sort(key=lambda x: x.published_at, reverse=True)
    return merged
