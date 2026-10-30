from datetime import datetime, timedelta
from dataclasses import replace

import pytest

from unified_scheduler.aggregation import Aggregator
from unified_scheduler.database import Repository
from unified_scheduler.models import Calendar, Event, SourceAccount
from unified_scheduler.reminders import ReminderService


@pytest.fixture
def context(tmp_path):
    repo = Repository(tmp_path / "reminders.sqlite3")
    event = Event("task", "local", "local", "local", "task", "Submit report",
                  "2026-10-30T10:30:00+08:00", "2026-10-30T10:30:00+08:00", kind="task")
    repo.save_local_event(event)
    now = datetime.fromisoformat("2026-10-30T10:00:00+08:00")
    return repo, event, now, ReminderService(repo, Aggregator(repo))


def test_reminder_due_once_and_survives_restart(context):
    repo, event, now, reminders = context
    assert reminders.due(now - timedelta(seconds=1), "Asia/Manila") == []
    assert [event.id for event in reminders.due(now, "Asia/Manila")] == [event.id]
    assert reminders.due(now + timedelta(minutes=1), "Asia/Manila") == []
    restarted_repo = Repository(repo.path)
    assert ReminderService(restarted_repo, Aggregator(restarted_repo)).due(now, "Asia/Manila") == []


def test_completed_tasks_do_not_notify(context):
    repo, event, now, reminders = context
    repo.set_completion(event.id, True)
    assert reminders.due(now, "Asia/Manila") == []


def test_snooze_delivers_once_then_stays_silent(context):
    repo, event, now, reminders = context
    assert reminders.due(now, "Asia/Manila")
    reminders.snooze(event.id, 10, now)
    assert reminders.due(now + timedelta(minutes=9), "Asia/Manila") == []
    assert reminders.due(now + timedelta(minutes=10), "Asia/Manila")
    assert reminders.due(now + timedelta(minutes=11), "Asia/Manila") == []
    reminders.dismiss(event.id)
    assert reminders.due(now + timedelta(hours=3), "Asia/Manila") == []


def test_configured_offset_and_disable(context):
    repo, event, now, reminders = context
    reminders.configure(event.id, 15)
    assert reminders.due(now, "Asia/Manila") == []
    assert reminders.due(now + timedelta(minutes=15), "Asia/Manila")
    reminders.configure(event.id, None)
    assert reminders.due(now + timedelta(hours=3), "Asia/Manila") == []


def test_overdue_task_alert_and_stale_appointment_suppression(context):
    repo, event, now, reminders = context
    repo.save_local_event(replace(event, start="2026-01-01T10:00:00+08:00", end="2026-01-01T10:00:00+08:00"))
    assert reminders.due(now, "Asia/Manila")
    repo.save_local_event(replace(event, id="old-meeting", uid="old-meeting", kind="event",
                                  start="2026-10-28T10:00:00+08:00", end="2026-10-28T11:00:00+08:00"))
    assert reminders.due(now, "Asia/Manila") == []


def test_all_day_reminder_uses_local_morning(context):
    repo, event, now, reminders = context
    repo.save_local_event(replace(event, start="2026-10-30", end="2026-10-31", all_day=True))
    before = now.replace(hour=8, minute=29)
    assert reminders.due(before, "Asia/Manila") == []
    assert reminders.due(before + timedelta(minutes=1), "Asia/Manila")


def test_changed_date_can_deliver_new_reminder(context):
    repo, event, now, reminders = context
    assert reminders.due(now, "Asia/Manila")
    repo.save_local_event(replace(event, start="2026-10-31T10:30:00+08:00", end="2026-10-31T10:30:00+08:00"))
    assert reminders.due(now + timedelta(days=1), "Asia/Manila")


def test_reminder_offset_is_elapsed_time_through_dst_fall_back(context):
    repo, event, _, reminders = context
    repo.save_local_event(replace(event, start="2026-11-01T01:15:00-05:00", end="2026-11-01T01:15:00-05:00",
                                  timezone="America/New_York"))
    assert reminders.due(datetime.fromisoformat("2026-11-01T01:44:00-04:00"), "America/New_York") == []
    assert reminders.due(datetime.fromisoformat("2026-11-01T01:45:00-04:00"), "America/New_York")


def test_snooze_is_elapsed_time_through_dst_fall_back(context):
    repo, event, _, reminders = context
    repo.save_local_event(replace(event, start="2026-11-01T01:50:00-04:00", end="2026-11-01T01:50:00-04:00",
                                  timezone="America/New_York"))
    now = datetime.fromisoformat("2026-11-01T01:55:00-04:00")
    assert reminders.due(now, "America/New_York")
    reminders.snooze(event.id, 10, now)
    assert reminders.due(datetime.fromisoformat("2026-11-01T01:04:00-05:00"), "America/New_York") == []
    assert reminders.due(datetime.fromisoformat("2026-11-01T01:05:00-05:00"), "America/New_York")
    assert reminders.due(datetime.fromisoformat("2026-11-01T01:06:00-05:00"), "America/New_York") == []


def test_cached_moodle_deadlines_get_one_overdue_notification(context):
    repo, event, now, reminders = context
    repo.set_completion(event.id, True)
    repo.save_account(SourceAccount("moodle", "moodle", "Academic deadlines"))
    repo.save_calendar(Calendar("moodle-feed", "moodle", "feed", "MOLE"))
    deadline = replace(event, id="moodle-deadline", source="moodle", account_id="moodle", calendar_id="moodle-feed",
                       kind="deadline", start="2026-08-01T10:00:00+08:00", end="2026-08-01T10:00:00+08:00")
    repo.replace_cached_events("moodle-feed", [deadline])
    assert [event.id for event in reminders.due(now, "Asia/Manila")] == [deadline.id]
    assert reminders.due(now + timedelta(minutes=1), "Asia/Manila") == []
