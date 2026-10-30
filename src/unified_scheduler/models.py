"""Provider-independent data models. Dates use ISO 8601; all-day ends are exclusive."""
from dataclasses import dataclass
from hashlib import sha256


@dataclass(slots=True)
class SourceAccount:
    id: str
    kind: str
    label: str
    identity: str = ""
    credential_key: str = ""
    status: str = "never"
    last_sync: str = ""
    error: str = ""


@dataclass(slots=True)
class Calendar:
    id: str
    account_id: str
    remote_id: str
    name: str
    color: str = "#4285F4"
    enabled: bool = True
    writable: bool = False


@dataclass(slots=True)
class Event:
    id: str
    source: str
    account_id: str
    calendar_id: str
    uid: str
    title: str
    start: str
    end: str
    all_day: bool = False
    description: str = ""
    location: str = ""
    url: str = ""
    kind: str = "event"
    priority: str = "Medium"
    status: str = "Pending"
    recurrence: str = ""
    reminder_minutes: int | None = 30
    task_id: str = ""
    category: str = ""
    color: str = ""
    timezone: str = ""


def stable_event_id(source: str, account_id: str, calendar_id: str,
                    uid: str, occurrence: str = "") -> str:
    """Names and event content never participate in identity."""
    raw = "\x1f".join((source, account_id, calendar_id, uid, occurrence))
    return f"{source}:{sha256(raw.encode('utf-8')).hexdigest()}"
