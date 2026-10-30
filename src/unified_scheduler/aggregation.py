"""Merge independent source occurrences without changing provider data."""
from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone as dt_timezone
from itertools import islice

from dateutil.rrule import DAILY, MONTHLY, WEEKLY, rrule
from dateutil.tz import datetime_exists

from .models import Event
from .timeutils import event_end, event_start, overlaps, zone


class Aggregator:
    def __init__(self, repo):
        self.repo = repo

    def events(self, start: date, end: date, timezone: str, calendar_ids=None,
               search: str = "", include_completed: bool = True,
               deduplicate: bool = False) -> list[Event]:
        if end <= start:
            return []
        zone(timezone)  # Fail clearly for invalid settings, rather than silently changing times.
        visible = {calendar.id for calendar in self.repo.list_calendars() if calendar.enabled}
        if calendar_ids is not None:
            visible.intersection_update(calendar_ids)
        completed = self.repo.completion_states()
        reminder_states = self.repo.reminder_states()
        query = search.casefold().strip()
        output = []
        for original in self.repo.list_local_events() + self.repo.list_cached_events():
            if original.calendar_id not in visible:
                continue
            if query and query not in f"{original.title}\n{original.description}".casefold():
                continue
            instances = self._local_instances(original, start, end, timezone) if original.source == "local" else [original]
            for event in instances:
                if not overlaps(event, start, end, timezone):
                    continue
                if event.id in completed:
                    event = replace(event, status="Completed" if completed[event.id] else
                                    (event.status if event.status != "Completed" else "Pending"))
                state = reminder_states.get(event.id)
                if state and state["configured"]:
                    event = replace(event, reminder_minutes=state["reminder_minutes"])
                if include_completed or event.status != "Completed":
                    output.append(event)
        if deduplicate:
            output = self._visual_dedup(output, timezone)
        output.sort(key=lambda event: (event_start(event, timezone).astimezone(dt_timezone.utc), not event.all_day,
                                       event.title.casefold(), event.id))
        return output

    @staticmethod
    def _local_instances(event, start, end, display_timezone):
        frequency = {"daily": DAILY, "weekly": WEEKLY, "monthly": MONTHLY}.get(event.recurrence.lower())
        if frequency is None:
            return [event]
        if event.all_day:
            recurrence_zone = zone(event.timezone or display_timezone)
            begins = datetime.combine(date.fromisoformat(event.start[:10]), time.min, recurrence_zone)
            finishes = datetime.combine(date.fromisoformat(event.end[:10]), time.min, recurrence_zone)
            duration = max(finishes - begins, timedelta(days=1))
        else:
            begins = datetime.fromisoformat(event.start.replace("Z", "+00:00"))
            if event.timezone:
                begins = begins.astimezone(zone(event.timezone)) if begins.tzinfo else begins.replace(tzinfo=zone(event.timezone))
            elif not begins.tzinfo:
                begins = begins.replace(tzinfo=zone(display_timezone))
            finishes = datetime.fromisoformat((event.end or event.start).replace("Z", "+00:00"))
            finishes = finishes.replace(tzinfo=begins.tzinfo) if not finishes.tzinfo else finishes.astimezone(begins.tzinfo)
            duration = finishes - begins
        lower = datetime.combine(start, time.min, zone(display_timezone)) - duration
        upper = datetime.combine(end, time.min, zone(display_timezone))
        schedule = rrule(frequency, dtstart=begins)
        instances = []
        # Bound iteration as a defensive measure for very large user date filters.
        for occurrence in islice(schedule.xafter(lower, inc=True), 50000):
            if occurrence >= upper:
                break
            if occurrence.replace(tzinfo=None) == begins.replace(tzinfo=None):
                occurrence = begins  # rrule drops fold=1; preserve the original instant.
            if not event.all_day and not datetime_exists(occurrence):
                continue  # RFC 5545: nonexistent local times do not form occurrences.
            stamp = occurrence.date().isoformat() if event.all_day else occurrence.isoformat()
            instance_end = (occurrence + duration).date().isoformat() if event.all_day else (occurrence + duration).isoformat()
            instances.append(replace(event, id=f"{event.id}@{stamp}", task_id=event.id,
                                     start=stamp, end=instance_end))
        return instances

    @staticmethod
    def _visual_dedup(events, timezone):
        """Only hide Google copies matching a Moodle iCalendar UID and exact occurrence."""
        def identity(event):
            start = event.start[:10] if event.all_day else event_start(event, timezone).isoformat()
            end = event.end[:10] if event.all_day else event_end(event, timezone).isoformat()
            return event.uid, event.all_day, start, end, event.title.strip().casefold()
        moodle = {identity(event) for event in events if event.source == "moodle" and event.uid}
        return [event for event in events if not (event.source == "google" and event.uid and identity(event) in moodle)]
