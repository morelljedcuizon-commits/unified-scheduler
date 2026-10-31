"""Google sign-in UX and credential isolation, without a browser or real accounts."""
from datetime import timedelta
import json
import os
from time import monotonic
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from google.oauth2.credentials import Credentials
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QLineEdit, QMessageBox, QPushButton

from unified_scheduler.database import Repository
from unified_scheduler.models import Calendar, Event, SourceAccount
from unified_scheduler.providers.errors import ProviderError
from unified_scheduler.providers.google import GoogleProvider, SCOPES
from unified_scheduler.ui.main_window import MainWindow
from unified_scheduler.ui.widgets import EventRow


class MemoryCredentials:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value):
        self.values[key] = value

    def delete(self, key):
        self.values.pop(key, None)


def wait_for(app, condition):
    deadline = monotonic() + 5
    while not condition() and monotonic() < deadline:
        QTest.qWait(10)
    app.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    assert condition(), "Google sign-in background work did not finish"


@pytest.fixture(scope="module")
def signin_app():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


@pytest.fixture
def signin_window(signin_app, tmp_path, monkeypatch):
    errors = []
    monkeypatch.setattr("sys.excepthook", lambda *error: errors.append(error))
    repo = Repository(tmp_path / "signin.sqlite3")
    repo.set_setting("timezone", "Asia/Manila")
    window = MainWindow(repo, MemoryCredentials(), smoke_test=True)
    window.show()
    signin_app.processEvents()
    yield window
    wait_for(signin_app, lambda: not window.busy)
    window.quitting = True
    window.close()
    window.deleteLater()
    signin_app.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    repo.close()
    assert not errors, f"Unhandled Qt callbacks: {errors}"


@pytest.mark.parametrize("reconnecting", [False, True])
def test_connect_and_reconnect_without_json_prompt_then_sync(
        signin_window, signin_app, monkeypatch, reconnecting):
    window = signin_window
    account = SourceAccount("google-test", "google", "person@example.com", status="connected")
    if reconnecting:
        window.repo.save_account(account)
    picker = Mock(side_effect=AssertionError("Sign-in must not ask users for a JSON file"))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", picker)
    warnings = Mock()
    monkeypatch.setattr(QMessageBox, "warning", warnings)

    def authorize(*args):
        window.repo.save_account(account)
        return account

    def sync(source, start, end, timezone):
        calendar = Calendar("google-calendar", source.id, "primary", "Personal")
        window.repo.save_calendar(calendar)
        today = window.today()
        event = Event("google-event", "google", source.id, calendar.id, "event", "Signed-in calendar event",
                      today.isoformat(), (today + timedelta(days=1)).isoformat(), all_day=True)
        window.repo.replace_cached_events(calendar.id, [event])
        return 1

    provider = Mock()
    provider.connect.side_effect = authorize
    provider.reconnect.side_effect = authorize
    provider.sync.side_effect = sync
    monkeypatch.setattr(window, "google_provider", lambda: provider)
    monkeypatch.setattr("unified_scheduler.sync.GoogleProvider", lambda *args: provider)

    window.connect_google(account=account if reconnecting else None)
    wait_for(signin_app, lambda: bool(provider.sync.call_count) and not window.busy)

    if reconnecting:
        provider.reconnect.assert_called_once_with(account.id)
        provider.connect.assert_not_called()
    else:
        provider.connect.assert_called_once_with()
        provider.reconnect.assert_not_called()
    picker.assert_not_called()
    warnings.assert_not_called()
    provider.sync.assert_called_once()
    assert window.repo.get_account(account.id).status == "synced"
    assert [row.entry.title for row in window.pages["Today"].findChildren(EventRow)] == ["Signed-in calendar event"]
    assert window.sync_button.isEnabled()


def test_settings_does_not_ask_for_oauth_configuration(signin_window, signin_app):
    legacy_path = "C:/missing/old-google-client.json"
    signin_window.repo.set_setting("google_client_config", legacy_path)
    signin_window.navigate("Settings")
    signin_app.processEvents()
    page = signin_window.pages["Settings"]
    assert all(edit.text() != legacy_path and "json" not in edit.placeholderText().lower()
               for edit in page.findChildren(QLineEdit))
    assert all("browse" not in button.text().lower() for button in page.findChildren(QPushButton))


@pytest.fixture
def oauth_session(tmp_path, monkeypatch):
    config = {"installed": {"client_id": "test.apps.googleusercontent.com",
                            "client_secret": "synthetic-desktop-value",
                            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                            "token_uri": "https://oauth2.googleapis.com/token"}}
    path = tmp_path / "client.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    credentials = MemoryCredentials()
    repo = Repository(tmp_path / "oauth.sqlite3")
    authorized = Credentials("access", refresh_token="refresh", id_token="synthetic-id-token",
                             scopes=list(SCOPES), client_id=config["installed"]["client_id"],
                             client_secret="synthetic-desktop-value", token_uri=config["installed"]["token_uri"])
    flow = Mock()
    flow.run_local_server.return_value = authorized
    monkeypatch.setattr("unified_scheduler.providers.google.DesktopFlow.from_client_config", Mock(return_value=flow))
    monkeypatch.setattr("unified_scheduler.providers.google.secrets.token_urlsafe", lambda _: "test-nonce")
    verify = Mock(return_value={"sub": "original-person", "email": "original@example.com",
                               "email_verified": True, "nonce": "test-nonce"})
    monkeypatch.setattr("unified_scheduler.providers.google.id_token.verify_oauth2_token", verify)
    yield GoogleProvider(repo, credentials), str(path), flow, verify
    repo.close()


def test_reconnect_different_google_account_preserves_vault_and_cache(oauth_session):
    provider, path, flow, verify = oauth_session
    account = provider.connect(path)
    calendar = Calendar("original-calendar", account.id, "primary", "Existing calendar")
    event = Event("cached-event", "google", account.id, calendar.id, "existing", "Keep this event",
                  "2026-10-30", "2026-10-31", all_day=True)
    provider.repo.save_calendar(calendar)
    provider.repo.replace_cached_events(calendar.id, [event])
    saved_credentials = provider.credentials.values.copy()
    saved_accounts = provider.repo.list_accounts()
    verify.return_value = {"sub": "different-person", "email": "different@example.com",
                           "email_verified": True, "nonce": "test-nonce"}

    with pytest.raises(ProviderError, match="different Google account"):
        provider.reconnect(account.id, path)

    assert provider.credentials.values == saved_credentials
    assert provider.repo.list_accounts() == saved_accounts
    assert provider.repo.list_calendars(account.id) == [calendar]
    assert provider.repo.list_cached_events() == [event]


@pytest.mark.parametrize("granted", [[], list(SCOPES[:2]), list(SCOPES[:-1]), [*SCOPES[:2], SCOPES[-1]]])
def test_denied_calendar_scope_does_not_store_account_or_tokens(oauth_session, granted):
    provider, path, flow, verify = oauth_session
    original = flow.run_local_server.return_value
    flow.run_local_server.return_value = Credentials(
        "access", refresh_token="refresh", id_token="synthetic-id-token",
        scopes=list(SCOPES), granted_scopes=granted, client_id=original.client_id,
        client_secret=original.client_secret, token_uri=original.token_uri,
    )

    with pytest.raises(ProviderError, match="Calendar read access was not granted"):
        provider.connect(path)

    assert provider.credentials.values == {}
    assert provider.repo.list_accounts() == []
    assert provider.repo.list_cached_events() == []


def test_legacy_calendar_grant_is_accepted_but_new_requests_are_narrow(oauth_session):
    provider, path, flow, verify = oauth_session
    original = flow.run_local_server.return_value
    flow.run_local_server.return_value = Credentials(
        "access", refresh_token="refresh", id_token="synthetic-id-token", scopes=list(SCOPES),
        granted_scopes=[*SCOPES[:2], "https://www.googleapis.com/auth/calendar.readonly"],
        client_id=original.client_id, client_secret=original.client_secret, token_uri=original.token_uri,
    )
    assert provider.connect(path).identity == "original-person"
    assert "https://www.googleapis.com/auth/calendar.readonly" not in SCOPES


def test_consent_denial_is_sanitized_and_does_not_store_credentials(oauth_session):
    from oauthlib.oauth2 import AccessDeniedError
    provider, path, flow, verify = oauth_session
    flow.run_local_server.side_effect = AccessDeniedError(description="synthetic-private-code")
    with pytest.raises(ProviderError, match="not approved") as error:
        provider.connect(path)
    assert "synthetic-private-code" not in str(error.value)
    assert provider.credentials.values == {}
    assert provider.repo.list_accounts() == []
