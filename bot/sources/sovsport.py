from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

import httpx

from bot.sources.dates_ru import parse_iso_z
from bot.sources.types import ExclusiveItem

logger = logging.getLogger(__name__)

LISTING_URL = "https://www.sovsport.ru/exclusive"
_BASE = "https://www.sovsport.ru"

_LISTING_RETRIES = 3
_LISTING_TIMEOUT = 60.0

_BUILD_ID_RE = re.compile(r'"buildId"\s*:\s*"([^"]+)"')


def _next_data_json(html: str) -> dict[str, Any] | None:
    m = re.search(
        r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
        html,
        re.DOTALL,
    )
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        logger.warning("Sovsport: __NEXT_DATA__ JSON parse failed")
        return None


def _build_id_from_html(html: str) -> str | None:
    m = _BUILD_ID_RE.search(html)
    return m.group(1) if m else None


def _page_props_from_next_root(data: dict[str, Any]) -> dict[str, Any]:
    pp = (data.get("props") or {}).get("pageProps")
    if isinstance(pp, dict):
        return pp
    pp2 = data.get("pageProps")
    return pp2 if isinstance(pp2, dict) else {}


def _article_url(item: dict[str, Any]) -> str | None:
    slug = (item.get("url") or "").strip().strip("/")
    if not slug or "/" in slug:
        return None
    sport = (item.get("sportCategory") or {}).get("typeId") or "football"
    raw_ct = (item.get("contentType") or {}).get("name")
    if raw_ct == "articles":
        segment = "articles"
    else:
        segment = "news"
    return f"{_BASE}/{sport}/{segment}/{slug}"


def _collect_blocks(page_props: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    articles = page_props.get("articles") or {}
    news = page_props.get("news") or {}
    for container in (articles, news):
        if not isinstance(container, dict):
            continue
        for _key, val in container.items():
            if isinstance(val, list):
                out.extend([x for x in val if isinstance(x, dict)])
    return out


async def _get_with_retries(
    client: httpx.AsyncClient,
    url: str,
    *,
    extra_headers: dict[str, str] | None = None,
) -> httpx.Response:
    last: BaseException | None = None
    merged = {**(extra_headers or {})}
    for attempt in range(_LISTING_RETRIES):
        try:
            r = await client.get(url, headers=merged, timeout=_LISTING_TIMEOUT)
            r.raise_for_status()
            return r
        except (
            httpx.ReadError,
            httpx.RemoteProtocolError,
            httpx.ConnectTimeout,
            httpx.ConnectError,
            httpx.TimeoutException,
        ) as e:
            last = e
            await asyncio.sleep(0.5 * (attempt + 1))
    assert last is not None
    raise last


async def _load_page_props(client: httpx.AsyncClient) -> dict[str, Any]:
    r = await _get_with_retries(client, LISTING_URL)
    html = r.text
    data = _next_data_json(html)
    props = _page_props_from_next_root(data) if data else {}
    blocks = _collect_blocks(props)
    if blocks:
        return props
    bid = (data.get("buildId") if data else None) or _build_id_from_html(html)
    if not bid:
        logger.warning("Sovsport: no buildId, exclusive.json fallback skipped")
        return props
    try:
        jr = await _get_with_retries(
            client,
            f"{_BASE}/_next/data/{bid}/exclusive.json",
            extra_headers={
                "x-nextjs-data": "1",
                "Referer": LISTING_URL,
                "Accept": "application/json",
            },
        )
        body = jr.json()
        props2 = body.get("pageProps") if isinstance(body, dict) else None
        if isinstance(props2, dict) and _collect_blocks(props2):
            return props2
    except Exception:
        logger.exception("Sovsport: exclusive.json fallback failed")
    return props


async def fetch_exclusive_items(client: httpx.AsyncClient) -> list[ExclusiveItem]:
    """
    Лента https://www.sovsport.ru/exclusive (Next.js).

    Пути вида /exclusive/2/ на сайте — не пагинация ленты, а редиректы на теги.

    Сначала разбор HTML (__NEXT_DATA__); если блоки пусты — запасной вариант
    GET /_next/data/{buildId}/exclusive.json (стабильнее при частичных ответах).
    """
    props = await _load_page_props(client)
    items: list[ExclusiveItem] = []
    seen: set[str] = set()
    for raw in _collect_blocks(props):
        slug = raw.get("url")
        title = (raw.get("title") or "").strip()
        pub = raw.get("publicPublishedAt")
        if not slug or not title or not pub:
            continue
        url = _article_url(raw)
        if not url:
            continue
        if url in seen:
            continue
        seen.add(url)
        dt = parse_iso_z(str(pub))
        if dt is None:
            continue
        items.append(ExclusiveItem(url=url, title=title, published_at=dt))
    items.sort(key=lambda x: x.published_at, reverse=True)
    return items
