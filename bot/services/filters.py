from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

# Title / rubric markers (case-insensitive substring match).
EXCLUDE_TITLE_SUBSTRINGS: tuple[str, ...] = (
    "mma",
    "ufc",
    "киберспорт",
    "кибер",
    "esports",
    "e-sport",
    "esport",
    "dota",
    "дота",
    "cs2",
    "cs:go",
    "cs go",
    "counter-strike",
    "counter strike",
    "valorant",
    "валорант",
    "киберспортив",
    "киберспорт ",
)


def normalize_url(url: str) -> str:
    """Strip fragment and UTM query params for deduplication."""
    raw = (url or "").strip()
    p = urlparse(raw)
    pairs = [
        (k, v)
        for k, v in parse_qsl(p.query, keep_blank_values=True)
        if not k.lower().startswith("utm_")
    ]
    path = p.path or "/"
    return urlunparse((p.scheme, p.netloc.lower(), path, "", urlencode(pairs), ""))


def title_excluded(title: str) -> bool:
    t = (title or "").casefold()
    return any(s in t for s in EXCLUDE_TITLE_SUBSTRINGS)
