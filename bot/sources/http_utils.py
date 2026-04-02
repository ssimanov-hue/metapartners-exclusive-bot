from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 MetapartnersExclusiveBot/1.0"
)


def default_headers() -> dict[str, str]:
    ua = os.environ.get("HTTP_USER_AGENT", DEFAULT_USER_AGENT)
    return {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.5",
    }


def create_client(**kwargs: Any) -> httpx.AsyncClient:
    # Сбор идёт по нескольким сайтам с десятками запросов подряд; 30s часто рвёт
    # выдачу на медленных сетях/Fly — тогда в отчёте пусто или только «Нет ответа».
    kw: dict[str, Any] = {
        "headers": default_headers(),
        "follow_redirects": True,
        "timeout": httpx.Timeout(120.0, connect=20.0),
    }
    kw.update(kwargs)
    return httpx.AsyncClient(**kw)
