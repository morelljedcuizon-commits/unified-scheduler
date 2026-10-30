"""Versioned SQLite persistence. Every operation owns a connection and transaction."""
from contextlib import contextmanager
from dataclasses import asdict
from datetime import date
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from .models import Calendar, Event, SourceAccount

SCHEMA_VERSION = 2


class Repository:
    def __init__(self, path):
        self.path = str(path)
        self._anchor = None
        self._uri = self.path == ":memory:"
        if self._uri:
            self.path = f"file:unified-{uuid4().hex}?mode=memory&cache=shared"
            self._anchor = sqlite3.connect(self.path, uri=True)
        else:
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(self.path, timeout=15, uri=self._uri)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=15000")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def initialize(self):
        with self._connection() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise RuntimeError("This database was created by a newer app. Upgrade before opening it.")
            if version == SCHEMA_VERSION:
                return
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("BEGIN IMMEDIATE")
            statements = [
                """CREATE TABLE IF NOT EXISTS source_accounts (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, label TEXT NOT NULL,
                    identity TEXT NOT NULL DEFAULT '', credential_key TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'never', last_sync TEXT NOT NULL DEFAULT '',
                    error TEXT NOT NULL DEFAULT '')""",
                """CREATE TABLE IF NOT EXISTS calendars (
                    id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES source_accounts(id) ON DELETE CASCADE,
                    remote_id TEXT NOT NULL, name TEXT NOT NULL, color TEXT NOT NULL,
                    enabled INTEGER NOT NULL, writable INTEGER NOT NULL,
                    UNIQUE(account_id, remote_id))""",
                """CREATE TABLE IF NOT EXISTS local_tasks (
                    id TEXT PRIMARY KEY, start TEXT NOT NULL, data_json TEXT NOT NULL)""",
                """CREATE TABLE IF NOT EXISTS cached_events (
                    id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL REFERENCES source_accounts(id) ON DELETE CASCADE,
                    calendar_id TEXT NOT NULL REFERENCES calendars(id) ON DELETE CASCADE,
                    start TEXT NOT NULL, data_json TEXT NOT NULL)""",
                "CREATE INDEX IF NOT EXISTS cached_calendar ON cached_events(calendar_id)",
                "CREATE INDEX IF NOT EXISTS cached_start ON cached_events(start)",
                "CREATE INDEX IF NOT EXISTS local_start ON local_tasks(start)",
                """CREATE TABLE IF NOT EXISTS event_ownership (
                    event_id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL REFERENCES source_accounts(id) ON DELETE CASCADE,
                    calendar_id TEXT NOT NULL REFERENCES calendars(id) ON DELETE CASCADE)""",
                """CREATE TABLE IF NOT EXISTS local_completion_status (
                    event_id TEXT PRIMARY KEY, completed INTEGER NOT NULL)""",
                """CREATE TABLE IF NOT EXISTS reminder_state (
                    event_id TEXT PRIMARY KEY, reminder_minutes INTEGER,
                    configured INTEGER NOT NULL DEFAULT 0,
                    notified_key TEXT NOT NULL DEFAULT '', dismissed INTEGER NOT NULL DEFAULT 0,
                    snoozed_until TEXT NOT NULL DEFAULT '')""",
                "CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value_json TEXT NOT NULL)",
            ]
            for statement in statements:
                conn.execute(statement)
            conn.execute("INSERT OR IGNORE INTO event_ownership SELECT id,account_id,calendar_id FROM cached_events")
            conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            conn.execute("INSERT OR IGNORE INTO source_accounts(id,kind,label,status) VALUES ('local','local','Local calendar','ready')")
            conn.execute("INSERT OR IGNORE INTO calendars VALUES ('local','local','local','Personal','#7275F3',1,1)")

    def close(self):
        if self._anchor:
            self._anchor.close()
            self._anchor = None

    def list_accounts(self):
        with self._connection() as conn:
            return [SourceAccount(**dict(row)) for row in conn.execute("SELECT * FROM source_accounts WHERE id != 'local' ORDER BY kind,label,id")]

    def get_account(self, account_id):
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM source_accounts WHERE id=?", (account_id,)).fetchone()
            return SourceAccount(**dict(row)) if row else None

    def save_account(self, account: SourceAccount):
        if account.kind not in {"local", "google", "moodle"}:
            raise ValueError("Unknown calendar provider.")
        if not account.id or not account.label.strip():
            raise ValueError("Account id and display name are required.")
        with self._connection() as conn:
            current = conn.execute("SELECT kind FROM source_accounts WHERE id=?", (account.id,)).fetchone()
            if current and current[0] != account.kind:
                raise ValueError("An account identity cannot change provider.")
            conn.execute("""INSERT INTO source_accounts VALUES (:id,:kind,:label,:identity,:credential_key,:status,:last_sync,:error)
                ON CONFLICT(id) DO UPDATE SET label=excluded.label,identity=excluded.identity,
                credential_key=excluded.credential_key,status=excluded.status,last_sync=excluded.last_sync,error=excluded.error""", asdict(account))

    def _delete_metadata(self, conn, event_ids):
        for event_id in event_ids:
            conn.execute("DELETE FROM local_completion_status WHERE event_id=? OR substr(event_id,1,?)=?",
                         (event_id, len(event_id) + 1, event_id + "@"))
            conn.execute("DELETE FROM reminder_state WHERE event_id=? OR substr(event_id,1,?)=?",
                         (event_id, len(event_id) + 1, event_id + "@"))

    def delete_account(self, account_id):
        if account_id == "local":
            raise ValueError("The local calendar cannot be removed.")
        with self._connection() as conn:
            ids = [row[0] for row in conn.execute("SELECT event_id FROM event_ownership WHERE account_id=?", (account_id,))]
            self._delete_metadata(conn, ids)
            conn.execute("DELETE FROM source_accounts WHERE id=?", (account_id,))

    def list_calendars(self, account_id=None):
        with self._connection() as conn:
            if account_id is None:
                rows = conn.execute("SELECT * FROM calendars ORDER BY account_id,name,id")
            else:
                rows = conn.execute("SELECT * FROM calendars WHERE account_id=? ORDER BY name,id", (account_id,))
            return [self._calendar(row) for row in rows]

    @staticmethod
    def _calendar(row):
        values = dict(row)
        values["enabled"], values["writable"] = bool(values["enabled"]), bool(values["writable"])
        return Calendar(**values)

    def get_calendar(self, calendar_id):
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM calendars WHERE id=?", (calendar_id,)).fetchone()
            return self._calendar(row) if row else None

    def save_calendar(self, calendar: Calendar):
        with self._connection() as conn:
            current = conn.execute("SELECT account_id FROM calendars WHERE id=?", (calendar.id,)).fetchone()
            if current and current[0] != calendar.account_id:
                raise ValueError("A calendar cannot be reassigned to a different account.")
            conn.execute("""INSERT INTO calendars VALUES (:id,:account_id,:remote_id,:name,:color,:enabled,:writable)
                ON CONFLICT(id) DO UPDATE SET remote_id=excluded.remote_id,name=excluded.name,
                color=excluded.color,enabled=excluded.enabled,writable=excluded.writable""", asdict(calendar))

    def delete_calendar(self, calendar_id):
        if calendar_id == "local":
            raise ValueError("The local calendar cannot be removed.")
        with self._connection() as conn:
            ids = [row[0] for row in conn.execute("SELECT event_id FROM event_ownership WHERE calendar_id=?", (calendar_id,))]
            self._delete_metadata(conn, ids)
            conn.execute("DELETE FROM calendars WHERE id=?", (calendar_id,))

    def replace_cached_events(self, calendar_id, events):
        events = list(events)
        with self._connection() as conn:
            calendar = conn.execute("SELECT account_id FROM calendars WHERE id=?", (calendar_id,)).fetchone()
            if not calendar or calendar_id == "local":
                raise ValueError("An external calendar is required.")
            ids = set()
            for event in events:
                if event.calendar_id != calendar_id or event.account_id != calendar[0] or event.source == "local":
                    raise ValueError("An event does not belong to this calendar/account.")
                if event.id in ids:
                    raise ValueError("The provider returned duplicate occurrence identities.")
                ids.add(event.id)
                existing = conn.execute("SELECT calendar_id FROM event_ownership WHERE event_id=?", (event.id,)).fetchone()
                if existing and existing[0] != calendar_id:
                    raise ValueError("Occurrence identity collides with another calendar.")
            # Replacement is atomic. Failures leave the previous successful cache intact.
            conn.execute("DELETE FROM cached_events WHERE calendar_id=?", (calendar_id,))
            conn.executemany("INSERT INTO cached_events VALUES (?,?,?,?,?)", [
                (event.id, event.account_id, calendar_id, event.start, json.dumps(asdict(event), ensure_ascii=False))
                for event in events
            ])
            conn.executemany("INSERT OR IGNORE INTO event_ownership VALUES (?,?,?)", [
                (event.id, event.account_id, calendar_id) for event in events
            ])
            # Preserve completion/reminder state for occurrences outside the rolling sync window.

    def save_local_event(self, event: Event):
        if event.source != "local" or event.account_id != "local" or event.calendar_id != "local":
            raise ValueError("Manual tasks must belong to the local calendar.")
        if not event.id or not event.title.strip():
            raise ValueError("A title is required.")
        if event.kind not in {"task", "event"}:
            raise ValueError("Choose task or event.")
        if event.status not in {"Pending", "In Progress", "Completed"}:
            raise ValueError("Invalid task status.")
        if event.priority not in {"Low", "Medium", "High"}:
            raise ValueError("Invalid task priority.")
        if event.recurrence.lower() not in {"", "none", "daily", "weekly", "monthly"}:
            raise ValueError("Unsupported recurrence.")
        from .timeutils import event_start, event_end
        if event.all_day and event.end and date.fromisoformat(event.end[:10]) <= date.fromisoformat(event.start[:10]):
            raise ValueError("An all-day end date must be after the start date (exclusive end).")
        begins, ends = event_start(event), event_end(event)
        if ends < begins:
            raise ValueError("The end must be at or after the start.")
        if event.reminder_minutes is not None and not 0 <= event.reminder_minutes <= 525600:
            raise ValueError("Invalid reminder offset.")
        with self._connection() as conn:
            conn.execute("""INSERT INTO local_tasks VALUES (?,?,?)
                ON CONFLICT(id) DO UPDATE SET start=excluded.start,data_json=excluded.data_json""",
                         (event.id, event.start, json.dumps(asdict(event), ensure_ascii=False)))
            if not event.recurrence or event.recurrence.lower() == "none":
                conn.execute("INSERT INTO local_completion_status VALUES (?,?) ON CONFLICT(event_id) DO UPDATE SET completed=excluded.completed",
                             (event.id, event.status == "Completed"))

    def delete_local_event(self, event_id):
        with self._connection() as conn:
            self._delete_metadata(conn, [event_id])
            conn.execute("DELETE FROM local_tasks WHERE id=?", (event_id,))

    def get_local_event(self, event_id):
        with self._connection() as conn:
            row = conn.execute("SELECT data_json FROM local_tasks WHERE id=?", (event_id,)).fetchone()
            return Event(**json.loads(row[0])) if row else None

    def list_local_events(self):
        with self._connection() as conn:
            return [Event(**json.loads(row[0])) for row in conn.execute("SELECT data_json FROM local_tasks ORDER BY start,id")]

    def list_cached_events(self):
        with self._connection() as conn:
            return [Event(**json.loads(row[0])) for row in conn.execute("SELECT data_json FROM cached_events ORDER BY start,id")]

    def set_completion(self, event_id, completed):
        with self._connection() as conn:
            conn.execute("INSERT INTO local_completion_status VALUES (?,?) ON CONFLICT(event_id) DO UPDATE SET completed=excluded.completed",
                         (event_id, bool(completed)))
            # Keep editor state consistent for non-recurring local tasks.
            row = conn.execute("SELECT data_json FROM local_tasks WHERE id=?", (event_id,)).fetchone()
            if row:
                payload = json.loads(row[0])
                payload["status"] = "Completed" if completed else "Pending"
                conn.execute("UPDATE local_tasks SET data_json=? WHERE id=?", (json.dumps(payload, ensure_ascii=False), event_id))

    def is_completed(self, event_id):
        return self.completion_states().get(event_id, False)

    def completion_states(self):
        with self._connection() as conn:
            return {row[0]: bool(row[1]) for row in conn.execute("SELECT event_id,completed FROM local_completion_status")}

    def set_setting(self, key, value):
        with self._connection() as conn:
            conn.execute("INSERT INTO app_settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json",
                         (key, json.dumps(value, ensure_ascii=False)))

    def get_setting(self, key, default=None):
        with self._connection() as conn:
            row = conn.execute("SELECT value_json FROM app_settings WHERE key=?", (key,)).fetchone()
            return json.loads(row[0]) if row else default

    def set_source_sync(self, account_id, status, error="", last_sync=""):
        with self._connection() as conn:
            conn.execute("""UPDATE source_accounts SET status=?,error=?,last_sync=CASE WHEN ?='' THEN last_sync ELSE ? END WHERE id=?""",
                         (status, error, last_sync, last_sync, account_id))

    def reminder_states(self):
        with self._connection() as conn:
            return {row["event_id"]: dict(row) for row in conn.execute("SELECT * FROM reminder_state")}

    def update_reminder(self, event_id, **changes):
        allowed = {"reminder_minutes", "configured", "notified_key", "dismissed", "snoozed_until"}
        if set(changes) - allowed:
            raise ValueError("Unknown reminder setting.")
        if not changes:
            return
        with self._connection() as conn:
            conn.execute("INSERT OR IGNORE INTO reminder_state(event_id) VALUES (?)", (event_id,))
            columns = ",".join(f"{key}=?" for key in changes)
            conn.execute(f"UPDATE reminder_state SET {columns} WHERE event_id=?", (*changes.values(), event_id))

    def claim_reminder(self, event_id, key):
        """Atomically claim a delivery so timer overlap/restarts cannot repeat it."""
        with self._connection() as conn:
            conn.execute("INSERT OR IGNORE INTO reminder_state(event_id) VALUES (?)", (event_id,))
            cursor = conn.execute("""UPDATE reminder_state SET notified_key=?,snoozed_until=''
                WHERE event_id=? AND notified_key!=? AND dismissed=0""", (key, event_id, key))
            return cursor.rowcount == 1
