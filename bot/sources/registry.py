from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date

import httpx

from bot.sources import euro_football, odds, rt_rss, sovsport, sportsdaily, vseprosport
from bot.sources.http_utils import create_client
from bot.sources.types import ExclusiveItem

logger = logging.getLogger(__name__)

SourceFn = Callable[..., Awaitable[list[ExclusiveItem]]]

SOURCE_REGISTRY: list[tuple[str, SourceFn]] = [
    ("sovsport", sovsport.fetch_exclusive_items),
    ("odds", odds.fetch_exclusive_items),
    ("sportsdaily", sportsdaily.fetch_exclusive_items),
    ("euro_football", euro_football.fetch_exclusive_items),
    ("vseprosport", vseprosport.fetch_exclusive_items),
    ("rt_rss", rt_rss.fetch_exclusive_items),
]

# Порядок секций в отчёте и подписи для пользователя
SOURCE_DISPLAY_NAMES: dict[str, str] = {
    "sovsport": "Советский спорт",
    "odds": "Odds.ru",
    "sportsdaily": "Sportsdaily",
    "euro_football": "Евро-футбол",
    "vseprosport": "ВсеПроСпорт",
    "rt_rss": "RT",
}

SOURCE_IDS_ORDER: list[str] = [sid for sid, _ in SOURCE_REGISTRY]


@dataclass
class SourceFetchResult:
    source_id: str
    items: list[ExclusiveItem] = field(default_factory=list)
    error: str | None = None


async def fetch_all_sources(
    client: httpx.AsyncClient | None = None,
    *,
    target_day: date | None = None,
) -> list[SourceFetchResult]:
    """Fetch all configured sources; failures are captured per source."""

    own_client = client is None
    client = client or create_client()
    rt_day = target_day or date.today()
    results: list[SourceFetchResult] = []
    try:
        for sid, fn in SOURCE_REGISTRY:
            try:
                if sid in (
                    "rt_rss",
                    "sportsdaily",
                    "odds",
                    "vseprosport",
                    "euro_football",
                ):
                    items = await fn(client, target_day=rt_day)
                else:
                    items = await fn(client)
                results.append(SourceFetchResult(source_id=sid, items=items))
            except Exception as e:
                logger.exception("Source %s failed", sid)
                results.append(SourceFetchResult(source_id=sid, error=str(e)))
    finally:
        if own_client:
            await client.aclose()
    return results


def _main_sync() -> None:
    logging.basicConfig(level=logging.INFO)

    async def run() -> None:
        out = await fetch_all_sources()
        for row in out:
            if row.error:
                print(row.source_id, "ERROR", row.error)
            else:
                print(row.source_id, len(row.items), "items")

    asyncio.run(run())


if __name__ == "__main__":
    _main_sync()
