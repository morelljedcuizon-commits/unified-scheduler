from dataclasses import replace
from datetime import date, datetime
import json
import sqlite3

import pytest

from unified_scheduler.aggregation import Aggregator
from unified_scheduler.credentials import CredentialError, CredentialStore
from unified_scheduler.database import Repository, SCHEMA_VERSION
from unified_scheduler.demo import seed_demo
from unified_scheduler.models import Calendar, Event, SourceAccount, stable_event_id
from unified_scheduler.timeutils import event_end, event_start, overlaps, parse_datetime


@pytest.fixture
def repo(tmp_path):
    return Repository(tmp_path / "scheduler.sqlite3")


def local(**kwargs):
    fields = dict(id="task-1", source="local", account_id="local", calendar_id="local", uid="task-1",
                  title="Write proposal", start="2026-10-30T10:30:00+08:00", end="2026-10-30T11:00:00+08:00",
                  kind="task", timezone="Asia/Manila")
    fields.update(kwargs)
    return Event(**fields)


def add_source(repo, account_id="account-a", calendar_id="calendar-a", kind="google"):
    repo.save_account(SourceAccount(account_id, kind, "Test account", credential_key="opaque-reference"))
    repo.save_calendar(Calendar(calendar_id, account_id, "primary", "Calendar"))
    return Event(stable_event_id(kind, account_id, calendar_id, "remote-1"), kind, account_id, calendar_id,
                 "remote-1", "Remote event", "2026-10-30T09:00:00Z", "2026-10-30T10:00:00Z")


def test_local_create_edit_complete_and_delete(repo):
    task = local(description="Draft the timeline", category="Study", color="#112233")
    repo.save_local_event(task)
    repo.save_local_event(replace(task, title="Revise proposal", status="In Progress"))
    assert len(repo.list_local_events()) == 1
    assert repo.get_local_event(task.id).title == "Revise proposal"
    assert repo.get_local_event(task.id).category == "Study"
    repo.set_completion(task.id, True)
    assert repo.is_completed(task.id)
    assert repo.get_local_event(task.id).status == "Completed"
    repo.set_completion(task.id, False)
    assert repo.get_local_event(task.id).status == "Pending"
    repo.delete_local_event(task.id)
    assert not repo.list_local_events()
    assert not repo.completion_states()


@pytest.mark.parametrize("change", [{"title": " "}, {"end": "2026-10-30T08:00:00+08:00"},
                                   {"status": "invalid"}, {"recurrence": "minutely"},
                                   {"source": "google"}])
def test_reject_invalid_local_events(repo, change):
    with pytest.raises(ValueError):
        repo.save_local_event(local(**change))


def test_calendar_and_search_filters(repo):
    repo.save_local_event(local(description="Research the module"))
    remote = add_source(repo)
    repo.replace_cached_events(remote.calendar_id, [remote])
    agg = Aggregator(repo)
    args = (date(2026, 10, 30), date(2026, 10, 31), "Asia/Manila")
    assert len(agg.events(*args)) == 2
    assert [event.source for event in agg.events(*args, search="MODULE")] == ["local"]
    assert [event.source for event in agg.events(*args, calendar_ids=[remote.calendar_id])] == ["google"]
    assert agg.events(*args, calendar_ids=[]) == []
    calendar = repo.get_calendar(remote.calendar_id)
    repo.save_calendar(replace(calendar, enabled=False))
    assert len(agg.events(*args)) == 1
    repo.set_completion("task-1", True)
    assert agg.events(*args, include_completed=False) == []


def test_multiday_all_day_exclusive_end_and_zone_independent_date(repo):
    task = local(start="2026-10-30", end="2026-11-02", all_day=True)
    repo.save_local_event(task)
    agg = Aggregator(repo)
    assert len(agg.events(date(2026, 11, 1), date(2026, 11, 2), "America/New_York")) == 1
    assert agg.events(date(2026, 11, 2), date(2026, 11, 3), "Asia/Manila") == []
    assert event_start(task, "America/New_York").date() == date(2026, 10, 30)
    assert event_end(task, "Asia/Manila").date() == date(2026, 11, 2)


def test_point_deadline_includes_start_but_not_next_day(repo):
    task = local(start="2026-10-30T00:00:00+08:00", end="2026-10-30T00:00:00+08:00")
    assert overlaps(task, date(2026, 10, 30), date(2026, 10, 31), "Asia/Manila")
    assert not overlaps(task, date(2026, 10, 29), date(2026, 10, 30), "Asia/Manila")


def test_recurrence_completion_is_per_occurrence(repo):
    repo.save_local_event(local(recurrence="daily"))
    agg = Aggregator(repo)
    args = (date(2026, 10, 30), date(2026, 11, 2), "Asia/Manila")
    instances = agg.events(*args)
    assert len(instances) == 3
    assert len({event.id for event in instances}) == 3
    assert all(event.task_id == "task-1" for event in instances)
    repo.set_completion(instances[0].id, True)
    assert len(agg.events(*args, include_completed=False)) == 2
    assert repo.get_local_event("task-1").status == "Pending"
    repo.delete_local_event("task-1")
    assert not repo.completion_states()


def test_local_recurrence_preserves_wall_time_across_dst_and_display_changes(repo):
    repo.save_local_event(local(start="2026-10-31T09:00:00-04:00", end="2026-10-31T10:00:00-04:00",
                                recurrence="daily", timezone="America/New_York"))
    agg = Aggregator(repo)
    instances = agg.events(date(2026, 10, 31), date(2026, 11, 3), "America/New_York")
    assert [event.start for event in instances] == ["2026-10-31T09:00:00-04:00", "2026-11-01T09:00:00-05:00", "2026-11-02T09:00:00-05:00"]
    other_zone = agg.events(date(2026, 10, 31), date(2026, 11, 3), "UTC")
    assert [event.id for event in instances] == [event.id for event in other_zone]
    assert parse_datetime(instances[1].start, "UTC").hour == 14


def test_monthly_recurrence_uses_calendar_rules(repo):
    repo.save_local_event(local(start="2026-01-31", end="2026-02-01", all_day=True, recurrence="monthly"))
    events = Aggregator(repo).events(date(2026, 1, 1), date(2026, 4, 1), "UTC")
    assert [event.start for event in events] == ["2026-01-31", "2026-03-31"]


def test_spring_dst_recurrence_skips_nonexistent_wall_time(repo):
    repo.save_local_event(local(start="2026-03-07T02:30:00-05:00", end="2026-03-07T03:00:00-05:00",
                                recurrence="daily", timezone="America/New_York"))
    events = Aggregator(repo).events(date(2026, 3, 7), date(2026, 3, 10), "America/New_York")
    assert [event.start for event in events] == ["2026-03-07T02:30:00-05:00", "2026-03-09T02:30:00-04:00"]


def test_dst_fall_back_start_fold_and_absolute_chronology(repo):
    repo.save_local_event(local(start="2026-11-01T01:15:00-05:00", end="2026-11-01T01:30:00-05:00",
                                recurrence="daily", timezone="America/New_York"))
    repo.save_local_event(local(id="earlier", uid="earlier", start="2026-11-01T01:45:00-04:00",
                                end="2026-11-01T01:50:00-04:00", timezone="America/New_York"))
    events = Aggregator(repo).events(date(2026, 11, 1), date(2026, 11, 2), "America/New_York")
    assert events[0].id == "earlier"
    assert events[1].start == "2026-11-01T01:15:00-05:00"


def test_all_day_local_event_rejects_nonexclusive_end(repo):
    with pytest.raises(ValueError, match="exclusive"):
        repo.save_local_event(local(start="2026-10-30", end="2026-10-30", all_day=True))


def test_repeated_sync_update_delete_and_offline_cache(repo):
    event = add_source(repo)
    for _ in range(3):
        repo.replace_cached_events(event.calendar_id, [event])
    assert len(repo.list_cached_events()) == 1
    repo.replace_cached_events(event.calendar_id, [replace(event, title="Changed", start="2026-10-31T09:00:00Z")])
    assert repo.list_cached_events()[0].title == "Changed"
    repo.set_source_sync(event.account_id, "offline", "Connection unavailable")
    assert len(repo.list_cached_events()) == 1
    assert Repository(repo.path).list_cached_events()[0].title == "Changed"
    repo.replace_cached_events(event.calendar_id, [])
    assert not repo.list_cached_events()


def test_account_isolation_and_transaction_rollback(repo):
    first = add_source(repo)
    second = add_source(repo, "account-b", "calendar-b")
    assert first.id != second.id
    repo.replace_cached_events(first.calendar_id, [first])
    repo.replace_cached_events(second.calendar_id, [second])
    with pytest.raises(ValueError):
        repo.replace_cached_events(first.calendar_id, [second])
    with pytest.raises(ValueError):
        repo.replace_cached_events(second.calendar_id, [replace(second, id=first.id)])
    with pytest.raises(ValueError):
        repo.replace_cached_events(first.calendar_id, [first, first])
    assert len(repo.list_cached_events()) == 2
    repo.delete_account(first.account_id)
    assert repo.list_cached_events() == [second]


def test_disconnect_removes_historical_completion_and_reminders(repo):
    event = add_source(repo)
    repo.replace_cached_events(event.calendar_id, [event])
    repo.set_completion(event.id, True)
    repo.update_reminder(event.id, dismissed=True)
    repo.replace_cached_events(event.calendar_id, [])  # occurrence rolled outside window
    assert repo.is_completed(event.id)
    repo.delete_account(event.account_id)
    assert not repo.completion_states()
    assert not repo.reminder_states()


def test_visual_dedup_requires_shared_uid_and_does_not_delete(repo):
    google = add_source(repo)
    moodle = add_source(repo, "moodle-a", "moodle-calendar", "moodle")
    repo.replace_cached_events(google.calendar_id, [google])
    repo.replace_cached_events(moodle.calendar_id, [moodle])
    agg = Aggregator(repo)
    args = (date(2026, 10, 30), date(2026, 10, 31), "UTC")
    assert len(agg.events(*args)) == 2
    assert [event.source for event in agg.events(*args, deduplicate=True)] == ["moodle"]
    assert len(repo.list_cached_events()) == 2
    repo.replace_cached_events(moodle.calendar_id, [replace(moodle, uid="different-uid")])
    assert len(agg.events(*args, deduplicate=True)) == 2


def test_settings_and_schema_version(repo):
    repo.set_setting("preferences", {"theme": "dark", "sync_minutes": 15})
    assert repo.get_setting("preferences")["theme"] == "dark"
    assert repo.get_setting("missing", 17) == 17
    with sqlite3.connect(repo.path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        conn.execute("PRAGMA user_version=999")
    with pytest.raises(RuntimeError, match="newer"):
        Repository(repo.path)


def test_version_one_migration_preserves_content(repo):
    event = add_source(repo)
    repo.replace_cached_events(event.calendar_id, [event])
    with sqlite3.connect(repo.path) as conn:
        conn.execute("DROP TABLE event_ownership")
        conn.execute("PRAGMA user_version=1")
    migrated = Repository(repo.path)
    assert migrated.list_cached_events() == [event]
    migrated.set_completion(event.id, True)
    migrated.delete_account(event.account_id)
    assert not migrated.completion_states()


class FakeVault:
    def __init__(self):
        self.entries = {}
        self.fail_manifest = False

    def get_password(self, service, key):
        return self.entries.get((service, key))

    def set_password(self, service, key, value):
        assert len(value.encode("utf-16-le")) <= 2560
        if self.fail_manifest and value.startswith(CredentialStore._PREFIX):
            raise RuntimeError("private failure with secret content")
        self.entries[service, key] = value

    def delete_password(self, service, key):
        del self.entries[service, key]


def test_credential_chunk_roundtrip_atomic_update_and_delete(monkeypatch):
    vault = FakeVault()
    store = CredentialStore()
    monkeypatch.setattr(store, "_backend", lambda: vault)
    value = json.dumps({"refresh_token": "secret" * 1200, "id_token": "😀" * 800}, ensure_ascii=False)
    store.set("account", value)
    assert store.get("account") == value
    count = len(vault.entries)
    vault.fail_manifest = True
    with pytest.raises(CredentialError) as caught:
        store.set("account", value + "changed")
    assert "secret" not in str(caught.value)
    assert store.get("account") == value
    assert len(vault.entries) == count
    vault.fail_manifest = False
    store.set("account", "https://moodle.example/?auth=private")
    assert len(vault.entries) == 1
    assert store.get("account").endswith("private")
    store.delete("account")
    assert not vault.entries
    store.delete("missing")


def test_demo_requires_empty_database_and_is_labeled(repo):
    seed_demo(repo, now=datetime.fromisoformat("2026-10-30T10:00:00+08:00"))
    assert repo.get_setting("demo_mode") is True
    assert all("DEMO" in account.label for account in repo.list_accounts())
    assert all(account.credential_key == "" for account in repo.list_accounts())
    assert len(repo.list_local_events()) >= 5
    assert len(repo.list_cached_events()) >= 5
    seed_demo(repo)  # restart is idempotent
    other = Repository(":memory:")
    other.save_local_event(local())
    with pytest.raises(ValueError, match="empty"):
        seed_demo(other)
    other.close()
