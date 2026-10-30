"""Provider orchestration; UI invokes this synchronous service in a worker thread."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as dt_timezone
from threading import Lock
from zoneinfo import ZoneInfo

from .providers.errors import OfflineError, ProviderError, ReauthenticationRequired
from .providers.google import GoogleProvider
from .providers.moodle import MoodleProvider


@dataclass(frozen=True)
class SyncResult:
    account_id: str
    label: str
    status: str
    count: int = 0
    error: str = ""


class SyncService:
    def __init__(self, repo, credentials, *, google=None, moodle=None):
        self.repo = repo
        self.google = google or GoogleProvider(repo, credentials)
        self.moodle = moodle or MoodleProvider(repo, credentials)
        self._lock = Lock()

    def sync_all(self) -> list[SyncResult]:
        if not self._lock.acquire(blocking=False):
            return []
        try:
            zone = self.repo.get_setting("timezone", "Asia/Manila")
            today = datetime.now(ZoneInfo(zone)).date()
            past = max(0, min(1825, int(self.repo.get_setting("sync_past_days", 30))))
            future = max(1, min(1825, int(self.repo.get_setting("sync_future_days", 180))))
            start, end = today - timedelta(days=past), today + timedelta(days=future + 1)
            results = []
            for account in self.repo.list_accounts():
                if account.kind not in ("google", "moodle"):
                    continue
                calendars = self.repo.list_calendars(account.id)
                if calendars and not any(calendar.enabled for calendar in calendars):
                    results.append(SyncResult(account.id, account.label, "disabled"))
                    continue
                try:
                    self.repo.set_source_sync(account.id, "syncing")
                    count = (self.google if account.kind == "google" else self.moodle).sync(account, start, end, zone)
                    self.repo.set_source_sync(account.id, "synced", last_sync=datetime.now(dt_timezone.utc).isoformat())
                    results.append(SyncResult(account.id, account.label, "synced", count))
                except ReauthenticationRequired as error:
                    self.repo.set_source_sync(account.id, "reauthenticate", error=str(error))
                    results.append(SyncResult(account.id, account.label, "reauthenticate", error=str(error)))
                except OfflineError as error:
                    self.repo.set_source_sync(account.id, "offline", error=str(error))
                    results.append(SyncResult(account.id, account.label, "offline", error=str(error)))
                except ProviderError as error:
                    self.repo.set_source_sync(account.id, "error", error=str(error))
                    results.append(SyncResult(account.id, account.label, "error", error=str(error)))
                except Exception:
                    # Keyring/library exceptions can embed secret response bodies. Do not log them.
                    message = "Synchronization failed. Check this source and its secure credentials; the cached calendar remains available."
                    self.repo.set_source_sync(account.id, "error", error=message)
                    results.append(SyncResult(account.id, account.label, "error", error=message))
            return results
        finally:
            self._lock.release()
