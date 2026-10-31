"""Account and workspace boundaries using synthetic credentials only."""
from datetime import datetime
import json
from unittest.mock import Mock

import pytest
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials

from unified_scheduler.credentials import CredentialStore
from unified_scheduler.database import Repository
from unified_scheduler.models import Calendar, Event, SourceAccount
from unified_scheduler.providers.google import GoogleProvider, SCOPES
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
    repository = Repository(tmp_path / "lifecycle.sqlite3")
    yield repository
    repository.close()


def cached_event(repo, account):
    calendar = Calendar("calendar-" + account.id, account.id, "primary", "Synthetic calendar")
    event = Event("event-" + account.id, account.kind, account.id, calendar.id,
                  "synthetic-event", "Synthetic cached event", "2026-10-30", "2026-10-31", all_day=True)
    repo.save_calendar(calendar)
    repo.replace_cached_events(calendar.id, [event])
    return event


def local_task(repo):
    task = Event("local-task", "local", "local", "local", "local-task", "Local work",
                 "2026-10-30", "2026-10-31", all_day=True, kind="task")
    repo.save_local_event(task)
    return task


def test_verified_multi_account_connect_and_disconnect_preserves_other_sources(repo, tmp_path, monkeypatch):
    config = {"installed": {"client_id": "test.apps.googleusercontent.com", "client_secret": "synthetic-desktop",
                            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                            "token_uri": "https://oauth2.googleapis.com/token"}}
    path = tmp_path / "synthetic-client.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setenv("UNIFIED_SCHEDULER_GOOGLE_CLIENT_CONFIG", str(path))
    monkeypatch.setattr("unified_scheduler.providers.google.secrets.token_urlsafe", lambda _: "synthetic-nonce")
    claims = Mock()
    monkeypatch.setattr("unified_scheduler.providers.google.id_token.verify_oauth2_token", claims)
    flow = Mock()
    monkeypatch.setattr("unified_scheduler.providers.google.DesktopFlow.from_client_config", Mock(return_value=flow))
    vault = MemoryCredentials()
    provider = GoogleProvider(repo, vault)
    accounts = []
    for identity in ("first", "second"):
        claims.return_value = {"sub": identity, "email": identity + "@example.com", "email_verified": True,
                               "nonce": "synthetic-nonce"}
        flow.run_local_server.return_value = Credentials(
            "synthetic-access-" + identity, refresh_token="synthetic-refresh-" + identity,
            id_token="synthetic-id-token", scopes=list(SCOPES),
            client_id=config["installed"]["client_id"], client_secret=config["installed"]["client_secret"],
            token_uri=config["installed"]["token_uri"],
        )
        accounts.append(provider.connect())
    assert accounts[0].id != accounts[1].id
    assert accounts[0].credential_key != accounts[1].credential_key
    first_event, second_event = [cached_event(repo, account) for account in accounts]
    repo.set_completion(first_event.id, True)
    repo.update_reminder(first_event.id, dismissed=True)
    moodle = SourceAccount("moodle", "moodle", "Synthetic feed", credential_key="moodle-url")
    repo.save_account(moodle)
    moodle_event = cached_event(repo, moodle)
    vault.set(moodle.credential_key, "https://example.invalid/feed?authtoken=synthetic")
    task = local_task(repo)
    second_token = vault.get(accounts[1].credential_key)

    provider.disconnect(accounts[0].id)

    assert repo.get_account(accounts[0].id) is None
    assert vault.get(accounts[0].credential_key) is None
    assert repo.get_account(accounts[1].id) == accounts[1]
    assert vault.get(accounts[1].credential_key) == second_token
    assert repo.get_account(moodle.id) == moodle
    assert vault.get(moodle.credential_key) is not None
    assert {event.id for event in repo.list_cached_events()} == {second_event.id, moodle_event.id}
    assert repo.list_local_events() == [task]
    assert first_event.id not in repo.completion_states()
    assert first_event.id not in repo.reminder_states()
    provider.disconnect(accounts[0].id)  # Repeated removal must not affect another account.
    assert len(vault.values) == 2


def test_revoked_token_preserves_cache_and_other_account_still_syncs(repo, monkeypatch):
    vault = MemoryCredentials()
    first = SourceAccount("first", "google", "First", credential_key="first-token")
    second = SourceAccount("second", "google", "Second", credential_key="second-token")
    for account in (first, second):
        repo.save_account(account)
        vault.set(account.credential_key, json.dumps({
            "refresh_token": "synthetic-refresh-" + account.id, "client_id": "synthetic-client",
            "client_secret": "synthetic-client-value", "token": "synthetic-expired",
            "expiry": "2000-01-01T00:00:00Z", "scopes": list(SCOPES),
        }))
    previous = cached_event(repo, first)
    task = local_task(repo)
    refresh_calls = []

    def refresh(credentials, request):
        refresh_calls.append(credentials.refresh_token)
        if credentials.refresh_token.endswith("first"):
            raise RefreshError("synthetic-private-error-details")
        credentials.token = "synthetic-renewed-access"
        credentials.expiry = datetime(2099, 1, 1)

    monkeypatch.setattr(Credentials, "refresh", refresh)
    browser = Mock(side_effect=AssertionError("Background refresh must not open a browser"))
    monkeypatch.setattr("unified_scheduler.providers.google.DesktopFlow.from_client_config", browser)
    service = Mock()
    service.calendarList.return_value.list.return_value.execute.return_value = {"items": []}
    factory = Mock(return_value=service)
    provider = GoogleProvider(repo, vault, service_factory=factory)

    results = {result.account_id: result for result in SyncService(repo, vault, google=provider).sync_all()}

    assert results[first.id].status == "reauthenticate"
    assert "synthetic-private-error-details" not in results[first.id].error
    assert results[second.id].status == "synced"
    assert repo.list_cached_events() == [previous]
    assert repo.list_local_events() == [task]
    assert len(refresh_calls) == 2
    assert json.loads(vault.get(second.credential_key))["token"] == "synthetic-renewed-access"
    factory.assert_called_once()
    browser.assert_not_called()


def test_vault_namespaces_keep_same_account_and_chunked_credentials_separate(monkeypatch):
    entries = {}
    backend = Mock()
    backend.get_password.side_effect = lambda service, key: entries.get((service, key))
    backend.set_password.side_effect = lambda service, key, value: entries.__setitem__((service, key), value)
    backend.delete_password.side_effect = lambda service, key: entries.pop((service, key), None)
    first = CredentialStore("UnifiedScheduler:synthetic-workspace-one")
    second = CredentialStore("UnifiedScheduler:synthetic-workspace-two")
    for store in (first, second):
        monkeypatch.setattr(store, "_backend", lambda: backend)
    first_value, second_value = "synthetic-first" * 100, "synthetic-second" * 100
    first.set("same-account", first_value)
    second.set("same-account", second_value)
    assert first.get("same-account") == first_value
    assert second.get("same-account") == second_value
    first.delete("same-account")
    assert first.get("same-account") is None
    assert second.get("same-account") == second_value
    assert all(service == second.service for service, key in entries)


def test_local_only_sync_never_calls_online_providers_or_vault(repo):
    task = local_task(repo)
    vault, google, moodle = Mock(), Mock(), Mock()
    assert SyncService(repo, vault, google=google, moodle=moodle).sync_all() == []
    assert repo.list_local_events() == [task]
    assert not vault.mock_calls
    assert not google.mock_calls
    assert not moodle.mock_calls
