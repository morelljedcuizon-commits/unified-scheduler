"""Persistent reminders, delivered by the GUI's tray while the application runs."""
from datetime import datetime, time, timedelta, timezone as dt_timezone
from hashlib import sha256

from .timeutils import event_start, parse_datetime, zone


class ReminderService:
    def __init__(self, repo, aggregator):
        self.repo = repo
        self.aggregator = aggregator

    def due(self, now: datetime, timezone: str) -> list:
        if now.tzinfo is None:
            raise ValueError("Reminder timestamps must have a timezone.")
        now = now.astimezone(zone(timezone))
        now_utc = now.astimezone(dt_timezone.utc)
        states = self.repo.reminder_states()
        # Longstanding tasks remain eligible for one overdue notification. Recurring
        # series only need a recent window, preventing years of historical alerts.
        start_date = now.date() - timedelta(days=30)
        for event in self.repo.list_local_events() + self.repo.list_cached_events():
            if not event.recurrence and event.kind in {"task", "deadline"}:
                start_date = min(start_date, event_start(event, timezone).date())
        candidates = self.aggregator.events(start_date, now.date() + timedelta(days=367),
                                            timezone, include_completed=False)
        due_events = []
        for event in candidates:
            state = states.get(event.id, {})
            if state.get("dismissed") or event.reminder_minutes is None:
                continue
            begins = event_start(event, timezone)
            # All-day dates have no midnight appointment: remind at 09:00 local time.
            if event.all_day:
                begins = datetime.combine(begins.date(), time(9), zone(timezone))
            begins_utc = begins.astimezone(dt_timezone.utc)
            trigger = begins_utc - timedelta(minutes=event.reminder_minutes)
            snooze = state.get("snoozed_until", "")
            key_payload = f"scheduled:{event.start}:{event.reminder_minutes}"
            if snooze:
                if now_utc < parse_datetime(snooze, "UTC"):
                    continue
            else:
                if now_utc < trigger:
                    continue
                # Historical appointments are not useful alerts; tasks remain overdue.
                if event.kind not in {"task", "deadline"} and now_utc - begins_utc > timedelta(hours=24):
                    continue
                # Skip stale repeated deadlines while still notifying today's occurrence.
                if event.task_id and now_utc - begins_utc > timedelta(days=1):
                    continue
            key = sha256(key_payload.encode()).hexdigest()
            if self.repo.claim_reminder(event.id, key):
                due_events.append(event)
            if len(due_events) >= 10:
                break  # Avoid an unbounded notification storm on first launch.
        return due_events

    def dismiss(self, event_id):
        self.repo.update_reminder(event_id, dismissed=True, snoozed_until="")

    def snooze(self, event_id, minutes=10, now=None):
        if not 1 <= minutes <= 10080:
            raise ValueError("Snooze must be between one minute and one week.")
        now = now or datetime.now(dt_timezone.utc)
        if now.tzinfo is None:
            raise ValueError("Snooze timestamps must have a timezone.")
        until = (now.astimezone(dt_timezone.utc) + timedelta(minutes=minutes)).isoformat()
        self.repo.update_reminder(event_id, dismissed=False, notified_key="", snoozed_until=until)

    def configure(self, event_id, minutes):
        if minutes is not None and not 0 <= minutes <= 525600:
            raise ValueError("Invalid reminder offset.")
        self.repo.update_reminder(event_id, reminder_minutes=minutes, configured=True,
                                 notified_key="", dismissed=False, snoozed_until="")
