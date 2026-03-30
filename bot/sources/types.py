from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ExclusiveItem:
    """Single exclusive material from a source listing."""

    url: str
    title: str
    published_at: datetime
    source_id: str = ""
