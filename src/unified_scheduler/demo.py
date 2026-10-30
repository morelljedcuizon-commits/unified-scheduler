"""Unmistakably labeled sample calendars for a separate, disposable demo database."""
from datetime import datetime, time, timedelta

from .models import Calendar, Event, SourceAccount
from .timeutils import zone


def seed_demo(repo, timezone="Asia/Manila", now=None):
    if repo.get_setting("demo_mode", False):
        return
    if repo.list_accounts() or repo.list_local_events() or repo.list_cached_events():
        raise ValueError("Demo data requires an empty, separate database.")
    now = now or datetime.now(zone(timezone))
    today = now.astimezone(zone(timezone)).date()
    repo.set_setting("demo_mode", True)
    repo.set_setting("onboarding_complete", True)
    repo.set_setting("timezone", timezone)
    repo.save_calendar(Calendar("local", "local", "local", "DEMO · Personal", "#7578F6"))
    google = SourceAccount("demo-google", "google", "DEMO · Campus Google", "demo@example.invalid", status="demo",
                           last_sync=now.isoformat(), error="Sample data · online sync disabled")
    moodle = SourceAccount("demo-moodle", "moodle", "DEMO · MOLE courses", status="demo",
                           last_sync=now.isoformat(), error="Sample data · online sync disabled")
    repo.save_account(google)
    repo.save_account(moodle)
    repo.save_calendar(Calendar("demo-google-calendar", google.id, "demo-primary", "DEMO · Classes", "#4F8DF7"))
    repo.save_calendar(Calendar("demo-moodle-calendar", moodle.id, "demo-feed", "DEMO · Academic deadlines", "#F4A34B"))

    def timed(day, hour, minute=0):
        return datetime.combine(today + timedelta(days=day), time(hour, minute), zone(timezone)).isoformat()

    def local(uid, title, day, hour, **kwargs):
        event = Event(uid, "local", "local", "local", uid, title, timed(day, hour), timed(day, hour, 30),
                      kind="task", timezone=timezone, **kwargs)
        repo.save_local_event(event)

    local("demo-local-overdue", "Review research notes", -1, 17,
          description="DEMO TASK · Review interview notes and draft three takeaways.", priority="High", category="Research")
    local("demo-local-plan", "Plan the day", 0, 8, status="Completed",
          description="DEMO TASK · Choose the three most useful things to finish today.", category="Personal")
    local("demo-local-proposal", "Finish the project proposal", 0, 11,
          description="DEMO TASK · Outline the problem, approach, and timeline.", priority="High", category="Coursework")
    local("demo-local-reading", "Read chapter 6", 0, 16,
          description="DEMO TASK · Read and write a short summary.", status="In Progress", category="Reading")
    local("demo-local-walk", "Take an afternoon walk", 1, 17,
          description="DEMO TASK · A short break outdoors.", priority="Low", recurrence="daily", category="Wellbeing")
    local("demo-local-outline", "Prepare next week's outline", 3, 10,
          description="DEMO TASK · Bring questions for the group discussion.", category="Coursework")
    google_events = [
        Event("demo-google-lab", "google", google.id, "demo-google-calendar", "demo-google-lab", "Software engineering lab",
              timed(0, 9), timed(0, 10, 30), description="DEMO EVENT · Team exercise and implementation review.", location="Engineering Building · Lab 2"),
        Event("demo-google-study", "google", google.id, "demo-google-calendar", "demo-google-study", "Study group",
              timed(0, 14), timed(0, 15), description="DEMO EVENT · Compare solutions and prepare questions.", location="Library · Collaboration room"),
        Event("demo-google-meeting", "google", google.id, "demo-google-calendar", "demo-google-meeting", "Project check-in",
              timed(2, 13), timed(2, 14), description="DEMO EVENT · Weekly team check-in."),
    ]
    moodle_events = [
        Event("demo-moodle-quiz", "moodle", moodle.id, "demo-moodle-calendar", "demo-moodle-quiz", "Algorithms quiz closes",
              timed(0, 23, 59), timed(0, 23, 59), kind="task", priority="High",
              description="DEMO DEADLINE · Locally marking this complete does not submit an assignment."),
        Event("demo-moodle-report", "moodle", moodle.id, "demo-moodle-calendar", "demo-moodle-report", "Lab report deadline",
              (today + timedelta(days=1)).isoformat(), (today + timedelta(days=2)).isoformat(), all_day=True, kind="task",
              description="DEMO DEADLINE · All-day academic deadline from a sample Moodle calendar."),
        Event("demo-moodle-reading", "moodle", moodle.id, "demo-moodle-calendar", "demo-moodle-reading", "Independent reading day",
              today.isoformat(), (today + timedelta(days=1)).isoformat(), all_day=True,
              description="DEMO EVENT · A date-only event, shown in the all-day section."),
    ]
    repo.replace_cached_events("demo-google-calendar", google_events)
    repo.replace_cached_events("demo-moodle-calendar", moodle_events)
