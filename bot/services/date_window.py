from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo


def day_bounds_utc(day: date, tz_name: str) -> tuple[datetime, datetime]:
    """Return [start, end) in UTC for the calendar *day* in *tz_name*."""
    tz = ZoneInfo(tz_name)
    start_local = datetime.combine(day, time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def in_day_window(published_at: datetime, start_utc: datetime, end_utc: datetime) -> bool:
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=UTC)
    t = published_at.astimezone(UTC)
    return start_utc <= t < end_utc
