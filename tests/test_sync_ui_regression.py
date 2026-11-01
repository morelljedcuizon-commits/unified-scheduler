"""Exercise a real asynchronous add-feed and refresh lifecycle without secrets."""
import os
from datetime import datetime, timedelta
from pathlib import Path
from time import monotonic
from zoneinfo import ZoneInfo

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, QTimer
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QPushButton

from unified_scheduler.database import Repository
from unified_scheduler.providers.moodle import MoodleProvider
from unified_scheduler.ui.dialogs import MoodleDialog
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


def wait_for(app, condition, seconds=4):
    deadline = monotonic() + seconds
    while not condition() and monotonic() < deadline:
        QTest.qWait(10)
    app.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    assert condition(), "The background operation did not complete in time"


def test_add_feed_test_save_and_background_sync_populates_dashboard(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    if Path("C:/Windows/Fonts/segoeui.ttf").is_file():
        QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    errors = []
    monkeypatch.setattr("sys.excepthook", lambda *error: errors.append(error))
    today = datetime.now(ZoneInfo("Asia/Manila")).date()
    payload = (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:synthetic-deadline\r\n"
        f"DTSTART;VALUE=DATE:{today:%Y%m%d}\r\n"
        f"DTEND;VALUE=DATE:{today + timedelta(days=1):%Y%m%d}\r\n"
        "SUMMARY:Freshly imported deadline\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
    ).encode()
    downloads = []

    def download(*args, **kwargs):
        downloads.append(True)
        return payload

    monkeypatch.setattr("unified_scheduler.providers.moodle.download_ics", download)
    repo = Repository(tmp_path / "async.sqlite3")
    repo.set_setting("timezone", "Asia/Manila")
    window = MainWindow(repo, MemoryCredentials(), smoke_test=True)
    original_exec = MoodleDialog.exec
    tested_counts = []

    def interact(dialog):
        def actions():
            try:
                dialog.name_edit.setText("Synthetic academic calendar")
                dialog.url_edit.setText("https://calendar.example.invalid/feed?authtoken=synthetic")
                dialog.test_connection()
                wait_for(app, lambda: dialog.worker is None)
                tested_counts.append(dialog.message.text())
                assert "1" in dialog.message.text()
                # A test is read-only. Only Save creates the subscription and leads
                # MainWindow.add_moodle to dispatch the initial background sync.
                assert not repo.list_accounts()
                assert not repo.list_cached_events()
                dialog.save()
            except BaseException as error:
                errors.append(error)
                QDialog.reject(dialog)

        QTimer.singleShot(0, actions)
        return original_exec(dialog)

    monkeypatch.setattr(MoodleDialog, "exec", interact)
    try:
        window.show()
        window.add_moodle()
        assert not errors
        wait_for(app, lambda: not window.busy)
        assert tested_counts
        assert len(downloads) == 2
        assert repo.list_accounts()[0].status == "synced"
        assert len(repo.list_cached_events()) == 1
        rows = window.pages["Today"].findChildren(EventRow)
        assert [row.entry.title for row in rows] == ["Freshly imported deadline"]
        assert window.sync_button.isEnabled()

        # A later explicit refresh updates the same identity and redraws the view.
        payload = payload.replace(b"Freshly imported deadline", b"Updated deadline")
        window.sync()
        wait_for(app, lambda: not window.busy)
        assert len(repo.list_cached_events()) == 1
        rows = window.pages["Today"].findChildren(EventRow)
        assert [row.entry.title for row in rows] == ["Updated deadline"]
        assert not errors
    finally:
        window.quitting = True
        window.close()
        window.deleteLater()
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        repo.close()


def test_fresh_local_workspace_does_not_enter_syncing_state(tmp_path):
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    repo = Repository(tmp_path / "fresh.sqlite3")
    window = MainWindow(repo, MemoryCredentials(), smoke_test=True)
    try:
        window.sync()
        assert not window.busy
        assert window.sync_button.isEnabled()
        actions = window.pages["Accounts"].findChildren(QPushButton)
        assert all(button.isEnabled() for button in actions
                   if button.text() in ("＋  Connect Google account", "＋  Add Moodle calendar"))
        assert "Connect a source" in window.statusBar().currentMessage()
    finally:
        window.quitting = True
        window.close()
        window.deleteLater()
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        repo.close()


def test_empty_personal_feed_explains_export_selection_without_saving(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    errors = []
    monkeypatch.setattr("sys.excepthook", lambda *error: errors.append(error))
    monkeypatch.setattr("unified_scheduler.providers.moodle.download_ics",
                        lambda *args, **kwargs: b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n")
    repo = Repository(tmp_path / "empty-test.sqlite3")
    repo.set_setting("timezone", "Asia/Manila")
    credentials = MemoryCredentials()
    dialog = MoodleDialog(None, MoodleProvider(repo, credentials), "Asia/Manila")
    try:
        dialog.url_edit.setText("https://moodle.example.invalid/calendar/export_execute.php?preset_what=user&authtoken=SYNTHETIC_SECRET")
        dialog.test_connection()
        wait_for(app, lambda: dialog.worker is None)
        message = dialog.message.text()
        assert "All events" in message
        assert "Connected successfully" not in message
        assert "SYNTHETIC_SECRET" not in message
        assert not repo.list_accounts()
        assert not repo.list_cached_events()
        assert not credentials.values
        assert not errors
    finally:
        dialog.deleteLater()
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        repo.close()


def test_connection_uses_configured_sync_window(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    errors = []
    monkeypatch.setattr("sys.excepthook", lambda *error: errors.append(error))
    today = datetime.now(ZoneInfo("Asia/Manila")).date()
    future = today + timedelta(days=270)
    payload = (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:future-deadline\r\n"
        f"DTSTART;VALUE=DATE:{future:%Y%m%d}\r\n"
        "SUMMARY:Next academic year\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
    ).encode()
    monkeypatch.setattr("unified_scheduler.providers.moodle.download_ics", lambda *args, **kwargs: payload)
    repo = Repository(tmp_path / "custom-window.sqlite3")
    repo.set_setting("timezone", "Asia/Manila")
    repo.set_setting("sync_past_days", 2)
    repo.set_setting("sync_future_days", 365)
    provider = MoodleProvider(repo, MemoryCredentials())
    inspected = []
    inspect_feed = provider.inspect_feed

    def capture_window(url, start, end, timezone):
        result = inspect_feed(url, start, end, timezone)
        inspected.append((start, end, timezone, len(result.events)))
        return result

    monkeypatch.setattr(provider, "inspect_feed", capture_window)
    dialog = MoodleDialog(None, provider, "Asia/Manila")
    try:
        dialog.url_edit.setText("https://calendar.example.invalid/feed")
        dialog.test_connection()
        wait_for(app, lambda: dialog.worker is None)
        assert inspected == [(today - timedelta(days=2), today + timedelta(days=366), "Asia/Manila", 1)]
        assert "1" in dialog.message.text()
        assert not errors
    finally:
        dialog.deleteLater()
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        repo.close()
