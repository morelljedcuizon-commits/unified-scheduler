"""Explicit timezone and exclusive end-date handling shared by the app."""
from datetime import date, datetime, time, timedelta, timezone as dt_timezone
import locale
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def zone(name: str) -> ZoneInfo:
    return ZoneInfo(name)


def default_timezone() -> str:
    language = locale.getlocale()[0] or ""
    if language.lower().endswith(("_ph", "_philippines")):
        return "Asia/Manila"
    try:
        from tzlocal import get_localzone_name
        name = get_localzone_name()
        ZoneInfo(name)
        return name
    except (ImportError, ZoneInfoNotFoundError, ValueError, OSError):
        return "UTC"


def parse_datetime(value: str, timezone: str = "UTC") -> datetime:
    """Floating local times are interpreted in the selected display timezone."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=zone(timezone))
    return parsed.astimezone(zone(timezone))


as_datetime = parse_datetime


def event_start(event, timezone: str = "UTC") -> datetime:
    if event.all_day:
        return datetime.combine(date.fromisoformat(event.start[:10]), time.min, zone(timezone))
    return parse_datetime(event.start, timezone)


def event_end(event, timezone: str = "UTC") -> datetime:
    if event.all_day:
        start = date.fromisoformat(event.start[:10])
        end = date.fromisoformat(event.end[:10]) if event.end else start + timedelta(days=1)
        if end <= start:
            end = start + timedelta(days=1)
        return datetime.combine(end, time.min, zone(timezone))
    return parse_datetime(event.end or event.start, timezone)


def overlaps(event, start: date, end: date, timezone: str) -> bool:
    lower = datetime.combine(start, time.min, zone(timezone))
    upper = datetime.combine(end, time.min, zone(timezone))
    begins, finishes = event_start(event, timezone), event_end(event, timezone)
    lower, upper, begins, finishes = [value.astimezone(dt_timezone.utc) for value in (lower, upper, begins, finishes)]
    if finishes <= begins:
        return lower <= begins < upper
    return begins < upper and finishes > lower
