from __future__ import annotations

from datetime import date, datetime

import httpx

from bot.services.date_window import day_bounds_utc, in_day_window
from bot.services.filters import normalize_url, title_excluded
from bot.sources.registry import SourceFetchResult, fetch_all_sources
from bot.sources.types import ExclusiveItem


async def collect_exclusives_for_day(
    day: date,
    tz_name: str,
    client: httpx.AsyncClient,
) -> tuple[list[ExclusiveItem], list[SourceFetchResult]]:
    """
    Fetch all sources, dedupe by normalized URL, drop MMA/cyber by title,
    keep items whose published_at falls in [start, end) for *day* in *tz_name*.
    """
    results = await fetch_all_sources(client, target_day=day)
    start_utc, end_utc = day_bounds_utc(day, tz_name)

    by_url: dict[str, ExclusiveItem] = {}
    for row in results:
        if row.error:
            continue
        for it in row.items:
            key = normalize_url(it.url)
            if key in by_url:
                continue
            if title_excluded(it.title):
                continue
            if not in_day_window(it.published_at, start_utc, end_utc):
                continue
            by_url[key] = ExclusiveItem(
                url=it.url.split("#", 1)[0],
                title=it.title,
                published_at=it.published_at,
                source_id=row.source_id,
            )

    items = sorted(by_url.values(), key=lambda x: x.published_at, reverse=True)
    return items, results
