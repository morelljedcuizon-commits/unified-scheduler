from datetime import date, datetime, timezone
from dataclasses import replace
import json
import logging
from unittest.mock import MagicMock, Mock

import pytest
import requests
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from googleapiclient.errors import HttpError
import httplib2

from unified_scheduler.database import Repository
from unified_scheduler.models import SourceAccount
from unified_scheduler.providers.errors import OfflineError, ProviderError, ReauthenticationRequired
from unified_scheduler.providers.google import GoogleProvider, SCOPES, normalize_event
from unified_scheduler.providers.moodle import MoodleProvider, download_ics, parse_ics, validate_url
from unified_scheduler.sync import SyncService


class MemoryCredentials:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value):
        self.values[key] = value

    def delete(self, key):
        self.values.pop(key, None)


@pytest.fixture
def repo(tmp_path):
    return Repository(tmp_path / "test.sqlite3")


def ics(*events):
    return ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Tests//Scheduler//EN\r\n"
            + "\r\n".join(events) + "\r\nEND:VCALENDAR\r\n").encode()


SINGLE = """BEGIN:VEVENT
UID:assignment-1
DTSTART;VALUE=DATE:20261030
DTEND;VALUE=DATE:20261031
SUMMARY:Assignment deadline
DESCRIPTION:Read chapter 4
LOCATION:Online
URL:https://moodle.example/mod/assign/view.php?id=12
END:VEVENT"""


def test_ics_all_day_exclusive_end():
    result = parse_ics(ics(SINGLE), "account", "calendar", date(2026, 10, 30), date(2026, 11, 1), "Asia/Manila")
    assert len(result) == 1
    assert result[0].all_day
    assert result[0].start == "2026-10-30"
    assert result[0].end == "2026-10-31"
    assert result[0].description == "Read chapter 4"
    assert result[0].location == "Online"


def test_ics_recurrence_modified_and_cancelled_instances():
    recurring = """BEGIN:VEVENT
UID:weekly
DTSTART;TZID=America/New_York:20261026T090000
DTEND;TZID=America/New_York:20261026T100000
RRULE:FREQ=WEEKLY;COUNT=3
SUMMARY:Weekly meeting
END:VEVENT"""
    moved = """BEGIN:VEVENT
UID:weekly
RECURRENCE-ID;TZID=America/New_York:20261102T090000
DTSTART;TZID=America/New_York:20261103T110000
DTEND;TZID=America/New_York:20261103T120000
SUMMARY:Moved meeting
END:VEVENT"""
    cancelled = """BEGIN:VEVENT
UID:weekly
RECURRENCE-ID;TZID=America/New_York:20261109T090000
DTSTART;TZID=America/New_York:20261109T090000
STATUS:CANCELLED
END:VEVENT"""
    events = parse_ics(ics(recurring, moved, cancelled), "a", "c", date(2026, 10, 20), date(2026, 11, 20), "Asia/Manila")
    assert len(events) == 2
    assert events[0].start.endswith("-04:00")
    assert events[1].start == "2026-11-03T11:00:00-05:00"
    moved_again = moved.replace("20261103T110000", "20261104T110000").replace("20261103T120000", "20261104T120000")
    updated = parse_ics(ics(recurring, moved_again, cancelled), "a", "c", date(2026, 10, 20), date(2026, 11, 20), "Asia/Manila")
    assert updated[1].id == events[1].id


@pytest.mark.parametrize("payload", [b"<html>Please login</html>", b"", b"not a calendar", b"BEGIN:VCALENDAR\ninvalid"])
def test_ics_invalid_response(payload):
    with pytest.raises(ProviderError):
        parse_ics(payload, "a", "c", date(2026, 10, 1), date(2026, 11, 1), "Asia/Manila")


def test_ics_cancelled_uid_only_series_tombstone():
    cancelled = "BEGIN:VEVENT\nUID:assignment-1\nSTATUS:CANCELLED\nEND:VEVENT"
    assert parse_ics(ics(cancelled), "a", "c", date(2026, 10, 1), date(2026, 11, 1), "Asia/Manila") == []


def test_ics_rejects_zero_interval_before_recurrence_expansion():
    payload = ics(SINGLE.replace("SUMMARY:", "RRULE:FREQ=DAILY;INTERVAL=0\nSUMMARY:"))
    with pytest.raises(ProviderError, match="interval"):
        parse_ics(payload, "a", "c", date(2026, 10, 1), date(2026, 11, 1), "Asia/Manila")


def test_recurring_identity_does_not_depend_on_display_timezone():
    first = dict(GOOGLE_EVENT, originalStartTime={"dateTime": "2026-10-30T09:00:00+08:00"})
    second = dict(GOOGLE_EVENT, originalStartTime={"dateTime": "2026-10-30T01:00:00+00:00"})
    assert normalize_event(first, "a", "c", "Asia/Manila").id == normalize_event(second, "a", "c", "UTC").id


@pytest.mark.parametrize("url", ["http://example.com/feed", "https://u:p@example.com/feed", "file:///feed", "https://example.com/feed#fragment"])
def test_private_url_validation_does_not_echo_input(url):
    with pytest.raises(ProviderError) as error:
        validate_url(url)
    assert url not in str(error.value)


def test_html_response_and_offline_errors_are_private():
    session = Mock()
    session.get.side_effect = requests.ConnectionError("https://moodle.example/?authtoken=VERY_SECRET")
    with pytest.raises(OfflineError) as error:
        download_ics("https://moodle.example/?authtoken=VERY_SECRET", session=session)
    assert "VERY_SECRET" not in str(error.value)


def test_transport_rejects_insecure_redirect_and_oversized_payload():
    session = MagicMock()
    response = session.get.return_value.__enter__.return_value
    response.status_code = 302
    response.headers = {"Location": "http://example.com/?authtoken=SECRET"}
    with pytest.raises(ProviderError):
        download_ics("https://example.com/feed", session=session)
    response.status_code = 200
    response.headers = {"Content-Length": str(6 * 1024 * 1024)}
    with pytest.raises(ProviderError, match="5 MiB"):
        download_ics("https://example.com/feed", session=session)


def test_moodle_reconciliation_and_url_confidentiality(repo, monkeypatch):
    credentials = MemoryCredentials()
    provider = MoodleProvider(repo, credentials)
    private_url = "https://moodle.example/calendar/export_execute.php?userid=42&authtoken=VERY_PRIVATE"
    account = provider.add_feed("My course", private_url)
    monkeypatch.setattr("unified_scheduler.providers.moodle.download_ics", lambda *args, **kwargs: ics(SINGLE))
    for _ in range(2):
        assert provider.sync(account, date(2026, 10, 1), date(2026, 11, 1), "Asia/Manila") == 1
    assert len(repo.list_cached_events()) == 1
    assert "VERY_PRIVATE" not in repr(repo.list_accounts())
    assert "VERY_PRIVATE" not in repr(repo.list_calendars())
    assert "VERY_PRIVATE" not in repr(repo.list_cached_events())
    original_id = repo.list_cached_events()[0].id
    monkeypatch.setattr("unified_scheduler.providers.moodle.download_ics", lambda *args, **kwargs: ics(SINGLE.replace("20261030", "20261029")))
    provider.sync(account, date(2026, 10, 1), date(2026, 11, 1), "Asia/Manila")
    assert repo.list_cached_events()[0].id == original_id
    monkeypatch.setattr("unified_scheduler.providers.moodle.download_ics", lambda *args, **kwargs: ics())
    provider.sync(account, date(2026, 10, 1), date(2026, 11, 1), "Asia/Manila")
    assert repo.list_cached_events() == []
    provider.remove(account.id)
    assert credentials.values == {}


def test_moodle_secret_embedded_in_feed_is_not_cached():
    private_url = "https://moodle.example/calendar/export_execute.php?authtoken=VERY_PRIVATE"
    payload = ics(SINGLE.replace("Read chapter 4", "Open " + private_url))
    event = parse_ics(payload, "a", "c", date(2026, 10, 1), date(2026, 11, 1), "Asia/Manila", private_url=private_url)[0]
    assert "VERY_PRIVATE" not in repr(event)


class FakeRequest:
    def __init__(self, result):
        self.result = result

    def execute(self, **kwargs):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class Resource:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def list(self, **kwargs):
        self.calls.append(kwargs)
        return FakeRequest(self.pages[kwargs.get("pageToken", "first")])


class FakeGoogle:
    def __init__(self, events):
        self.calendar_resource = Resource({"first": {"items": [{"id": "shared@example.com", "summary": "Shared", "accessRole": "owner"}]}})
        self.event_resource = Resource(events)

    def calendarList(self):
        return self.calendar_resource

    def events(self):
        return self.event_resource


GOOGLE_EVENT = {"id": "event-same", "iCalUID": "uid-same", "summary": "Meeting",
                "start": {"dateTime": "2026-10-30T09:00:00+08:00"},
                "end": {"dateTime": "2026-10-30T10:00:00+08:00"}}


def google_provider(repo, credentials, fake):
    provider = GoogleProvider(repo, credentials, service_factory=lambda _: fake, sleep=lambda _: None)
    provider._load_credentials = lambda _: Mock(to_json=lambda: "{}")
    return provider


def test_google_accounts_isolated_pagination_deleted_and_repeat_sync(repo):
    credentials = MemoryCredentials()
    fake = FakeGoogle({"first": {"items": [GOOGLE_EVENT], "nextPageToken": "second"},
                       "second": {"items": [{"id": "gone", "status": "cancelled"}]}})
    provider = google_provider(repo, credentials, fake)
    for identity in ("account-1", "account-2"):
        account = SourceAccount(id=identity, kind="google", label=identity, credential_key=identity)
        repo.save_account(account)
        for _ in range(2):
            assert provider.sync(account, date(2026, 10, 1), date(2026, 11, 1), "Asia/Manila") == 1
    assert len(repo.list_cached_events()) == 2
    assert len({event.id for event in repo.list_cached_events()}) == 2
    assert len(repo.list_calendars("account-1")) == 1
    assert any(call.get("pageToken") == "second" for call in fake.event_resource.calls)
    assert all(call["singleEvents"] and not call["showDeleted"] for call in fake.event_resource.calls)
    fake.event_resource.pages = {"first": {"items": []}}
    provider.sync(repo.get_account("account-1"), date(2026, 10, 1), date(2026, 11, 1), "Asia/Manila")
    assert len(repo.list_cached_events()) == 1
    assert repo.list_cached_events()[0].account_id == "account-2"


def test_google_failure_preserves_cache_and_sets_offline(repo):
    credentials = MemoryCredentials()
    fake = FakeGoogle({"first": {"items": [GOOGLE_EVENT]}})
    provider = google_provider(repo, credentials, fake)
    account = SourceAccount(id="account", kind="google", label="Google", credential_key="token")
    repo.save_account(account)
    provider.sync(account, date(2026, 10, 1), date(2026, 11, 1), "Asia/Manila")
    fake.event_resource.pages = {"first": OSError("private transport details")}
    result = SyncService(repo, credentials, google=provider).sync_all()
    assert result[0].status == "offline"
    assert len(repo.list_cached_events()) == 1
    assert "private" not in result[0].error


def test_expired_token_refresh_and_reauthentication(repo, monkeypatch):
    credentials = MemoryCredentials()
    account = SourceAccount(id="account", kind="google", label="Google", credential_key="token")
    credentials.set("token", json.dumps({"refresh_token": "private-refresh", "client_id": "client", "client_secret": "secret", "token": "expired", "expiry": "2000-01-01T00:00:00Z"}))
    provider = GoogleProvider(repo, credentials)
    called = []

    def refresh(self, request):
        called.append(True)
        self.token = "new-access"
        self.expiry = datetime(2099, 1, 1)

    monkeypatch.setattr(Credentials, "refresh", refresh)
    assert provider._load_credentials(account).token == "new-access"
    assert called
    assert "new-access" in credentials.get("token")
    credentials.set("token", json.dumps({"refresh_token": "revoked", "client_id": "client", "client_secret": "secret"}))
    monkeypatch.setattr(Credentials, "refresh", Mock(side_effect=RefreshError("private token details")))
    with pytest.raises(ReauthenticationRequired) as error:
        provider._load_credentials(account)
    assert "private token" not in str(error.value)


def test_google_normalization_all_day_and_zone():
    all_day = normalize_event({"id": "day", "start": {"date": "2026-10-30"}, "end": {"date": "2026-10-31"}}, "a", "c", "Asia/Manila")
    assert all_day.all_day and all_day.end == "2026-10-31"
    timed = normalize_event({"id": "time", "start": {"dateTime": "2026-11-02T09:00:00", "timeZone": "America/New_York"}}, "a", "c", "Asia/Manila")
    assert timed.start.endswith("-05:00")


def test_reauth_status_reaches_account(repo):
    credentials = MemoryCredentials()
    account = SourceAccount(id="account", kind="google", label="Google", credential_key="missing")
    repo.save_account(account)
    result = SyncService(repo, credentials).sync_all()
    assert result[0].status == "reauthenticate"
    assert repo.get_account("account").status == "reauthenticate"


def test_google_oauth_pkce_verified_identity_and_account_selection(repo, tmp_path, monkeypatch):
    config = {"installed": {"client_id": "test.apps.googleusercontent.com", "client_secret": "desktop-client-value",
                            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                            "token_uri": "https://oauth2.googleapis.com/token"}}
    path = tmp_path / "client.json"
    path.write_text(json.dumps(config))
    credentials = MemoryCredentials()
    authorized = Credentials("access", refresh_token="refresh", id_token="signed-token", scopes=list(SCOPES),
                             client_id=config["installed"]["client_id"], client_secret="desktop-client-value",
                             token_uri="https://oauth2.googleapis.com/token")
    flow = Mock()
    flow.run_local_server.return_value = authorized
    factory = Mock(return_value=flow)
    monkeypatch.setattr("unified_scheduler.providers.google.DesktopFlow.from_client_config", factory)
    monkeypatch.setattr("unified_scheduler.providers.google.secrets.token_urlsafe", lambda _: "expected-nonce")
    verify = Mock(return_value={"sub": "verified-subject", "email": "person@example.com", "email_verified": True, "nonce": "expected-nonce"})
    monkeypatch.setattr("unified_scheduler.providers.google.id_token.verify_oauth2_token", verify)
    account = GoogleProvider(repo, credentials).connect(str(path))
    assert account.identity == "verified-subject"
    assert account.label == "person@example.com"
    assert factory.call_args.kwargs["autogenerate_code_verifier"] is True
    assert flow.run_local_server.call_args.kwargs["host"] == "127.0.0.1"
    assert flow.run_local_server.call_args.kwargs["port"] == 0
    assert flow.run_local_server.call_args.kwargs["prompt"] == "select_account consent"
    assert flow.run_local_server.call_args.kwargs["nonce"] == "expected-nonce"
    assert "signed-token" not in credentials.get(account.credential_key)
    assert "refresh" in credentials.get(account.credential_key)
    assert "refresh" not in repr(repo.list_accounts())
    verify.return_value["nonce"] = "incorrect-nonce"
    with pytest.raises(ProviderError, match="verified"):
        GoogleProvider(repo, credentials).connect(str(path))
    assert len(repo.list_accounts()) == 1


def test_default_reminders_off_for_both_providers(repo, monkeypatch):
    repo.set_setting("default_reminder", None)
    credentials = MemoryCredentials()
    moodle = MoodleProvider(repo, credentials)
    account = moodle.add_feed("Course", "https://example.com/feed?authtoken=private")
    monkeypatch.setattr("unified_scheduler.providers.moodle.download_ics", lambda *args, **kwargs: ics(SINGLE))
    moodle.sync(account, date(2026, 10, 1), date(2026, 11, 1), "Asia/Manila")
    account = SourceAccount(id="google", kind="google", label="Google", credential_key="google")
    repo.save_account(account)
    google_provider(repo, credentials, FakeGoogle({"first": {"items": [GOOGLE_EVENT]}})).sync(
        account, date(2026, 10, 1), date(2026, 11, 1), "Asia/Manila")
    assert len(repo.list_cached_events()) == 2
    assert all(event.reminder_minutes is None for event in repo.list_cached_events())


def test_google_custom_colors_hidden_and_vanished_calendars(repo):
    credentials = MemoryCredentials()
    account = SourceAccount(id="google", kind="google", label="Google", credential_key="google")
    repo.save_account(account)
    fake = FakeGoogle({"first": {"items": [GOOGLE_EVENT]}})
    provider = google_provider(repo, credentials, fake)
    provider.sync(account, date(2026, 10, 1), date(2026, 11, 1), "Asia/Manila")
    calendar = repo.list_calendars(account.id)[0]
    repo.save_calendar(replace(calendar, enabled=False, color="#123456"))
    fake.event_resource.calls.clear()
    provider.sync(account, date(2026, 10, 1), date(2026, 11, 1), "Asia/Manila")
    assert fake.event_resource.calls == []
    assert len(repo.list_cached_events()) == 1
    assert repo.get_calendar(calendar.id).color == "#123456"
    assert not repo.get_calendar(calendar.id).enabled
    fake.calendar_resource.pages = {"first": {"items": [], "nextPageToken": "second"}, "second": {"items": []}}
    provider.sync(account, date(2026, 10, 1), date(2026, 11, 1), "Asia/Manila")
    assert repo.list_calendars(account.id) == []
    assert repo.list_cached_events() == []


def test_google_backoff_is_bounded_and_errors_are_sanitized(repo):
    waits = []
    provider = GoogleProvider(repo, MemoryCredentials(), sleep=waits.append)
    error = HttpError(httplib2.Response({"status": "429"}), b'{"error":{"message":"private-secret"}}')
    request = Mock()
    request.execute.side_effect = [error, error, {"items": []}]
    assert provider._execute(request) == {"items": []}
    assert len(waits) == 2
    assert all(0 < wait <= 8 for wait in waits)
    waits.clear()
    request.execute.side_effect = error
    with pytest.raises(ProviderError, match="limiting") as caught:
        provider._execute(request)
    assert len(waits) == 3
    assert "private-secret" not in str(caught.value)
    assert logging.getLogger("google_auth_oauthlib.flow").disabled


def test_google_pagination_failure_does_not_remove_vanished_calendar(repo):
    credentials = MemoryCredentials()
    account = SourceAccount(id="google", kind="google", label="Google", credential_key="google")
    repo.save_account(account)
    fake = FakeGoogle({"first": {"items": [GOOGLE_EVENT]}})
    provider = google_provider(repo, credentials, fake)
    provider.sync(account, date(2026, 10, 1), date(2026, 11, 1), "Asia/Manila")
    fake.calendar_resource.pages = {"first": {"items": [], "nextPageToken": "second"}, "second": OSError("offline")}
    with pytest.raises(OfflineError):
        provider.sync(account, date(2026, 10, 1), date(2026, 11, 1), "Asia/Manila")
    assert len(repo.list_calendars(account.id)) == 1
    assert len(repo.list_cached_events()) == 1
