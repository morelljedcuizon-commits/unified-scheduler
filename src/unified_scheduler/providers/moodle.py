"""Private Moodle subscriptions, HTTPS transport and bounded ICS expansion."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta, timezone as dt_timezone
import re
from urllib.parse import parse_qsl, unquote, urljoin, urlsplit
from uuid import uuid4
from zoneinfo import ZoneInfo

import icalendar
import recurring_ical_events
import requests

from ..models import Calendar, Event, SourceAccount, stable_event_id
from .errors import OfflineError, ProviderError

MAX_ICS_BYTES = 5 * 1024 * 1024
MAX_OCCURRENCES = 20_000
MAX_COMPONENTS = 10_000


@dataclass(frozen=True)
class FeedInspection:
    """Safe connection feedback without private subscription details."""

    events: list[Event]
    raw_event_count: int
    message: str


def _inspection_message(raw_count: int, occurrence_count: int, personal_only: bool) -> str:
    if raw_count == 0:
        message = "Moodle returned no events."
        if personal_only:
            message += " This URL exports personal events only."
        return message + " In Moodle, export All events and choose a date range that includes your deadlines, then replace the saved URL."
    if occurrence_count == 0:
        message = (f"The feed contains {raw_count} event(s), but no active occurrences in the selected date window. "
                   "Check Moodle's exported date range and the sync date window in Settings.")
    else:
        message = f"{occurrence_count} occurrence(s) available in the selected date window."
    if personal_only:
        message += " This URL exports personal events only; export All events in Moodle to include academic deadlines."
    return message


def validate_url(url: str) -> str:
    """Private URLs remain opaque and are never included in validation errors."""
    url = url.strip()
    try:
        parsed = urlsplit(url)
        if (parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username
                or parsed.password or parsed.fragment or any(c.isspace() for c in url)):
            raise ValueError
        _ = parsed.port
    except (ValueError, TypeError):
        raise ProviderError("Enter a complete HTTPS calendar export URL without a username, password or fragment.") from None
    return url


def _scrub(value, private_url: str | None = None) -> str:
    result = str(value or "")
    if private_url:
        result = result.replace(private_url, "[private calendar URL]")
        for key, secret in parse_qsl(urlsplit(private_url).query):
            if secret and any(word in key.lower() for word in ("token", "auth", "secret", "key", "password")):
                result = result.replace(secret, "[private]").replace(unquote(secret), "[private]")
    # A calendar export address must never become an event hyperlink or description.
    return re.sub(r"https?://[^\s<>\"]*export_execute\.php[^\s<>\"]*", "[private calendar URL]", result, flags=re.I)


def _event_url(value, private_url=None) -> str:
    value = _scrub(value, private_url)
    try:
        parts = urlsplit(value)
        if parts.scheme not in ("https", "http") or not parts.hostname or parts.username:
            return ""
        if any(any(word in key.lower() for word in ("token", "auth", "secret", "password"))
               for key, _ in parse_qsl(parts.query)):
            return ""
        return value
    except ValueError:
        return ""


def download_ics(url: str, *, session=None) -> bytes:
    """Read at most 5 MiB decompressed, with certificate validation and HTTPS redirects."""
    current = validate_url(url)
    owned = session is None
    session = session or requests.Session()
    try:
        for _ in range(4):
            try:
                with session.get(current, stream=True, allow_redirects=False,
                                 timeout=(10, 30), headers={"Accept": "text/calendar"}, verify=True) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        target = response.headers.get("Location")
                        if not target:
                            raise ProviderError("The calendar server returned an invalid redirect.")
                        current = validate_url(urljoin(current, target))
                        continue
                    if response.status_code in (401, 403, 404, 410):
                        raise ProviderError("The private calendar URL is inaccessible or expired. Generate a new Moodle export URL.")
                    if response.status_code == 429:
                        raise ProviderError("Moodle is limiting requests. The cached calendar is available; try again later.")
                    if response.status_code != 200:
                        raise ProviderError("The calendar server could not provide the feed. Try again later.")
                    size = response.headers.get("Content-Length", "")
                    if size.isdigit() and int(size) > MAX_ICS_BYTES:
                        raise ProviderError("This calendar exceeds the 5 MiB download limit. Export a shorter date range.")
                    chunks = bytearray()
                    for chunk in response.iter_content(chunk_size=64 * 1024):
                        if len(chunks) + len(chunk) > MAX_ICS_BYTES:
                            raise ProviderError("This calendar exceeds the 5 MiB download limit. Export a shorter date range.")
                        chunks.extend(chunk)
                    return bytes(chunks)
            except requests.RequestException:
                raise OfflineError("Unable to reach Moodle securely. Check your connection; cached events remain available.") from None
        raise ProviderError("The calendar URL redirects too many times. Use the direct Moodle export URL.")
    finally:
        if owned:
            session.close()


def _aware(value: datetime | date, timezone: ZoneInfo) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone)
    return datetime.combine(value, time.min, timezone)


def parse_ics(payload: bytes, account_id: str, calendar_id: str, start: date, end: date,
              timezone: str, *, private_url: str | None = None,
              reminder_minutes: int | None = 30) -> list[Event]:
    """Expand a bounded half-open window; identities use the original recurrence ID."""
    if len(payload) > MAX_ICS_BYTES:
        raise ProviderError("This calendar exceeds the 5 MiB limit.")
    if not payload.lstrip(b"\xef\xbb\xbf \t\r\n").upper().startswith(b"BEGIN:VCALENDAR"):
        raise ProviderError("The URL returned HTML or another format instead of ICS. Use Moodle's private Export Calendar URL.")
    if end <= start or (end - start).days > 3653:
        raise ProviderError("The synchronization date window must be between one day and ten years.")
    try:
        calendar = icalendar.Calendar.from_ical(payload)
        if calendar.name != "VCALENDAR":
            raise ValueError
        components = calendar.walk("VEVENT")
        if len(components) > MAX_COMPONENTS:
            raise ProviderError("This calendar contains too many events. Export a shorter date range.")
        zone = ZoneInfo(str(calendar.get("X-WR-TIMEZONE", timezone)))
    except ProviderError:
        raise
    except Exception:
        raise ProviderError("The server returned an invalid ICS calendar or an unsupported time zone.") from None
    # A cancelled series may be represented by a UID-only tombstone.
    cancelled_uids = {str(component.get("UID", "")) for component in components
                      if str(component.get("STATUS", "")).upper() == "CANCELLED"
                      and not component.get("RECURRENCE-ID")}
    if cancelled_uids:
        calendar.subcomponents = [component for component in calendar.subcomponents
                                  if component.name != "VEVENT" or str(component.get("UID", "")) not in cancelled_uids]
        components = calendar.walk("VEVENT")
    recurring = set()
    for component in components:
        if not component.get("UID"):
            raise ProviderError("An event is missing its UID. Ask the calendar provider to correct the export.")
        if component.get("RRULE") or component.get("RDATE") or component.get("RECURRENCE-ID"):
            recurring.add(str(component.get("UID")))
        if component.get("STATUS") == "CANCELLED" and not component.get("DTSTART") and component.get("RECURRENCE-ID"):
            component.add("DTSTART", component["RECURRENCE-ID"].dt)
        if not component.get("DTSTART"):
            raise ProviderError("An event is missing its start date. Ask the calendar provider to correct the export.")
        # Avoid pathological high-frequency feeds before the recurrence engine expands them.
        rules = component.get("RRULE", {})
        if rules:
            frequency = str(rules.get("FREQ", [""])[0]).upper()
            try:
                interval = int(rules.get("INTERVAL", [1])[0])
                if interval < 1:
                    raise ValueError
            except (ValueError, TypeError):
                raise ProviderError("The ICS calendar contains an invalid recurrence interval.") from None
            period = {"SECONDLY": 1, "MINUTELY": 60, "HOURLY": 3600}.get(frequency)
            if period and (end - start).total_seconds() / (period * interval) > MAX_OCCURRENCES:
                raise ProviderError("This feed repeats too frequently. Export a shorter range or reduce its recurrence frequency.")
    window_start = datetime.combine(start, time.min, ZoneInfo(timezone))
    window_end = datetime.combine(end, time.min, ZoneInfo(timezone))
    results = {}
    try:
        query = recurring_ical_events.of(calendar, keep_recurrence_attributes=True)
        for index, component in enumerate(query.after(window_start)):
            if index >= MAX_OCCURRENCES:
                raise ProviderError("This date window contains too many occurrences. Export or synchronize a shorter range.")
            begin = component["DTSTART"].dt
            all_day = not isinstance(begin, datetime)
            finish = component["DTEND"].dt if component.get("DTEND") else begin + (timedelta(days=1) if all_day else timedelta())
            begin_aware, finish_aware = _aware(begin, zone), _aware(finish, zone)
            if begin_aware >= window_end:
                break
            if finish_aware < window_start or (finish_aware == window_start and begin_aware < window_start):
                continue
            if str(component.get("STATUS", "")).upper() == "CANCELLED":
                continue
            uid = str(component["UID"])
            recurrence_id = component.get("RECURRENCE-ID")
            instance = ""
            if recurrence_id and uid in recurring:
                recurrence_date = recurrence_id.dt
                instance = (_aware(recurrence_date, zone).astimezone(dt_timezone.utc).isoformat()
                            if isinstance(recurrence_date, datetime) else recurrence_date.isoformat())
            event_id = stable_event_id("moodle", account_id, calendar_id, uid, instance)
            results[event_id] = Event(
                id=event_id, source="moodle", account_id=account_id, calendar_id=calendar_id,
                uid=_scrub(uid, private_url), title=_scrub(component.get("SUMMARY", "Untitled event"), private_url),
                start=begin.isoformat() if all_day else begin_aware.isoformat(),
                end=finish.isoformat() if all_day else finish_aware.isoformat(), all_day=all_day,
                description=_scrub(component.get("DESCRIPTION", ""), private_url),
                location=_scrub(component.get("LOCATION", ""), private_url),
                url=_event_url(component.get("URL", ""), private_url), kind="deadline",
                reminder_minutes=reminder_minutes,
            )
    except ProviderError:
        raise
    except Exception:
        raise ProviderError("The ICS calendar contains invalid dates or recurrence rules. Its previous cache has been preserved.") from None
    return sorted(results.values(), key=lambda event: event.start)


class MoodleProvider:
    def __init__(self, repo, credentials, *, session=None):
        self.repo, self.credentials, self.session = repo, credentials, session

    def inspect_feed(self, url: str, start: date, end: date, timezone: str, *,
                     account_id: str = "test", calendar_id: str = "test") -> FeedInspection:
        """Fetch once and explain empty exports separately from date-window filtering."""
        url = validate_url(url)
        payload = download_ics(url, session=self.session)
        reminder = self.repo.get_setting("default_reminder", 30)
        reminder = int(reminder) if reminder is not None else None
        events = parse_ics(payload, account_id, calendar_id, start, end, timezone,
                           private_url=url, reminder_minutes=reminder)
        # parse_ics has already validated and bounded this payload. Count source
        # records separately: a recurring master can yield many visible occurrences.
        raw_count = len(icalendar.Calendar.from_ical(payload).walk("VEVENT"))
        personal_only = any(key.casefold() == "preset_what" and value.casefold() == "user"
                            for key, value in parse_qsl(urlsplit(url).query))
        return FeedInspection(events, raw_count,
                              _inspection_message(raw_count, len(events), personal_only))

    def test_connection(self, url: str, start: date, end: date, timezone: str) -> list[Event]:
        return self.inspect_feed(url, start, end, timezone).events

    def add_feed(self, label: str, url: str, color: str = "#10B981") -> SourceAccount:
        if not label.strip():
            raise ProviderError("Give this Moodle calendar a display name.")
        url = validate_url(url)
        identity = str(uuid4())
        key = "moodle:" + identity
        account = SourceAccount(id=identity, kind="moodle", label=label.strip(), credential_key=key)
        self.credentials.set(key, url)
        try:
            self.repo.save_account(account)
            self.repo.save_calendar(Calendar(id="moodle:" + identity, account_id=identity,
                                            remote_id="feed", name=label.strip(), color=color))
        except Exception:
            self.credentials.delete(key)
            self.repo.delete_account(identity)
            raise
        return account

    def edit_feed(self, account_id: str, label: str, url: str | None = None, color: str | None = None):
        account = self.repo.get_account(account_id)
        if not account or account.kind != "moodle":
            raise ProviderError("This Moodle calendar no longer exists.")
        if not label.strip():
            raise ProviderError("Give this Moodle calendar a display name.")
        if url:
            self.credentials.set(account.credential_key, validate_url(url))
        self.repo.save_account(replace(account, label=label.strip()))
        for calendar in self.repo.list_calendars(account_id):
            self.repo.save_calendar(replace(calendar, name=label.strip(), color=color or calendar.color))

    def sync(self, account: SourceAccount, start: date, end: date, timezone: str) -> int:
        url = self.credentials.get(account.credential_key)
        if not url:
            raise ProviderError("The private URL is missing from Windows Credential Manager. Edit this calendar and enter the URL again.")
        calendars = self.repo.list_calendars(account.id)
        if not calendars or not calendars[0].enabled:
            return 0
        calendar = calendars[0]
        inspection = self.inspect_feed(url, start, end, timezone,
                                       account_id=account.id, calendar_id=calendar.id)
        events = inspection.events
        self.repo.replace_cached_events(calendar.id, events)
        self.repo.set_setting("feed_sync:" + account.id, {
            "event_count": len(events), "raw_event_count": inspection.raw_event_count,
            "message": inspection.message, "window_start": start.isoformat(),
            "window_end": end.isoformat(),
        })
        return len(events)

    def remove(self, account_id: str):
        account = self.repo.get_account(account_id)
        if account:
            self.credentials.delete(account.credential_key)
            self.repo.delete_account(account_id)
            self.repo.set_setting("feed_sync:" + account_id, None)
