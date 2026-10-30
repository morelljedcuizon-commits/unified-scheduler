"""Native-widget integration checks; no real accounts or OS credential access."""
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication, QDate, QEvent, Qt, QTime
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication, QCheckBox, QDialog, QLabel, QListWidget

from unified_scheduler.aggregation import Aggregator
from unified_scheduler.database import Repository
from unified_scheduler.demo import seed_demo
from unified_scheduler.ui.dialogs import TaskDialog
from unified_scheduler.ui.main_window import MainWindow
from unified_scheduler.ui.widgets import EventRow


class NoCredentials:
    def __getattr__(self, name):
        raise AssertionError("The offline/demo UI must not access credentials")


def settle(app):
    app.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    if os.path.isfile("C:/Windows/Fonts/segoeui.ttf"):
        QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    return app


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    callback_errors = []
    monkeypatch.setattr("sys.excepthook", lambda *error: callback_errors.append(error))
    repo = Repository(tmp_path / "ui.sqlite3")
    seed_demo(repo, "Asia/Manila")
    widget = MainWindow(repo, NoCredentials(), demo=True, smoke_test=True)
    widget.show()
    settle(qapp)
    yield widget
    widget.quitting = True
    widget.close()
    widget.deleteLater()
    settle(qapp)
    repo.close()
    assert not callback_errors, f"Unhandled Qt callback failures: {callback_errors}"


def test_navigation_calendar_views_and_demo_network_guard(window, qapp):
    assert window.current_page == "Today"
    assert window.pages["Today"].findChildren(EventRow)
    for page in ("Today", "Upcoming", "Tasks", "Accounts", "Settings", "Calendar"):
        window.nav[page].click()
        settle(qapp)
        assert window.stack.currentWidget() is window.pages[page]
        assert window.heading.text() == page

    for mode, rows, columns in (("Day", 25, 1), ("Week", 25, 7), ("Month", 6, 7), ("Agenda", 1, 1)):
        window.calendar_view.mode_box.setCurrentText(mode)
        settle(qapp)
        table = window.calendar_view.table
        assert (table.rowCount(), table.columnCount()) == (rows, columns)
        displayed = [listing.item(i).data(Qt.UserRole)
                     for listing in table.findChildren(QListWidget)
                     for i in range(listing.count()) if listing.item(i).data(Qt.UserRole)]
        assert any(entry.id == "demo-google-lab" for entry in displayed)
        assert any(entry.id == "demo-moodle-reading" for entry in displayed)

    window.sync()
    assert not window.busy
    assert "disabled" in window.statusBar().currentMessage().lower()


@pytest.mark.parametrize("event_id", ["demo-local-proposal", "demo-moodle-quiz"])
def test_details_completion_is_persistent_and_external_cache_is_unchanged(window, qapp, event_id):
    today = window.today()
    event = next(e for e in window.aggregator.events(today, today + timedelta(days=1), window.timezone) if e.id == event_id)
    before = {e.id: e.status for e in window.repo.list_cached_events()}
    window.show_detail(event)
    settle(qapp)
    detail = window.detail_scroll.widget()
    if event.source != "local":
        assert any("does not submit work" in label.text() for label in detail.findChildren(QLabel))
    completion = next(check for check in detail.findChildren(QCheckBox) if check.text() == "Completed locally")
    completion.click()
    settle(qapp)
    restored_repo = Repository(window.repo.path)
    try:
        restored = next(e for e in Aggregator(restored_repo).events(today, today + timedelta(days=1), window.timezone) if e.id == event_id)
        assert restored.status == "Completed"
        assert {e.id: e.status for e in restored_repo.list_cached_events()} == before
    finally:
        restored_repo.close()
    window.show_completed.setChecked(False)
    settle(qapp)
    assert event_id not in {row.entry.id for row in window.pages["Today"].findChildren(EventRow)}


def test_calendar_visibility_and_source_search_filters(window, qapp):
    window.navigate("Accounts")
    settle(qapp)
    toggle = next(check for check in window.pages["Accounts"].findChildren(QCheckBox)
                  if check.text() == "DEMO · Classes")
    toggle.click()
    settle(qapp)
    assert not window.repo.get_calendar("demo-google-calendar").enabled
    assert any(e.source == "google" for e in window.repo.list_cached_events())
    window.navigate("Today")
    settle(qapp)
    assert all(row.entry.source != "google" for row in window.pages["Today"].findChildren(EventRow))
    window.source_filter.setCurrentIndex(window.source_filter.findData("source:moodle"))
    window.search.setText("submit an assignment")
    window.refresh_content()
    settle(qapp)
    assert {row.entry.id for row in window.pages["Today"].findChildren(EventRow)} == {"demo-moodle-quiz"}


def test_task_form_validation_and_all_day_round_trip(qapp):
    dialog = TaskDialog(None, "Asia/Manila", selected_date=datetime(2026, 10, 30).date())
    try:
        dialog.save()
        assert dialog.result_event is None
        assert "title" in dialog.error.text().lower()
        dialog.title_edit.setText("Multi-day workshop")
        dialog.kind.setCurrentText("Event")
        dialog.start_time.setTime(QTime(14, 0))
        dialog.end_time.setTime(QTime(13, 0))
        dialog.save()
        assert dialog.result_event is None
        assert "after" in dialog.error.text().lower()
        dialog.all_day.setChecked(True)
        dialog.end_date.setDate(QDate(2026, 11, 1))
        dialog.description.setPlainText("<b>Plain event text</b>")
        dialog.reminder.setCurrentIndex(dialog.reminder.findData(-1))
        dialog.save()
        entry = dialog.result_event
        assert dialog.result() == QDialog.Accepted
        assert entry.start == "2026-10-30" and entry.end == "2026-11-02"
        assert entry.all_day and entry.reminder_minutes is None
        assert entry.description == "<b>Plain event text</b>"
        edit = TaskDialog(None, "Asia/Manila", event=entry)
        try:
            assert edit.end_date.date() == QDate(2026, 11, 1)
            assert edit.reminder.currentData() == -1
            edit.title_edit.setText("Updated workshop")
            edit.save()
            assert edit.result_event.id == entry.id
            assert edit.result_event.title == "Updated workshop"
            assert edit.result_event.end == "2026-11-02"
        finally:
            edit.deleteLater()
    finally:
        dialog.deleteLater()
        settle(qapp)


def test_task_form_rejects_nonexistent_dst_time(qapp):
    dialog = TaskDialog(None, "America/New_York", selected_date=datetime(2026, 3, 8).date())
    try:
        dialog.title_edit.setText("Spring clock change")
        dialog.start_time.setTime(QTime(2, 30))
        dialog.save()
        assert dialog.result_event is None
        assert "daylight-saving" in dialog.error.text()
        dialog.start_time.setTime(QTime(3, 30))
        dialog.save()
        assert dialog.result_event is not None
        assert datetime.fromisoformat(dialog.result_event.start).utcoffset() == timedelta(hours=-4)
    finally:
        dialog.deleteLater()
        settle(qapp)
