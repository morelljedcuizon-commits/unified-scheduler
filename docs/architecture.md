# Architecture and data lifecycle

Unified Scheduler is a local native Qt application. The UI uses services for persistence, aggregation and online providers; it does not embed a browser or require a hosted backend.

## Module responsibilities

| Module | Responsibility |
| --- | --- |
| `__main__` | CLI, per-user data directory, first launch, demo isolation and application lifecycle |
| `ui` | Navigation, Qt widgets, task/source dialogs, event details, settings and worker dispatch |
| `models` | Shared source account, calendar and event dataclasses |
| `database` | Versioned schema, parameterized queries and atomic persistence |
| `aggregation` | Calendar visibility, range/text filtering, local recurrence, completion decoration and display deduplication |
| `timeutils` | ISO date/time interpretation and display timezone helpers |
| `credentials` | Windows Credential Manager access through `keyring` |
| `google_oauth` | Resolve and validate the app-owned Google Desktop OAuth configuration |
| `providers.google` | Desktop OAuth, verified account identities, calendar listing and Google event polling |
| `providers.moodle` | HTTPS feed download, ICS validation and recurrence expansion |
| `sync` | Configured polling window and per-source success/failure state |
| `reminders` | Persistent eligibility, delivery deduplication, completion, dismissal and snooze |
| `demo` | Explicitly labeled sample records in an isolated temporary database |

Network work runs outside the Qt UI thread. The repository opens short-lived SQLite connections for its methods rather than sharing a UI-thread connection with workers. A provider fetch completes before its successful calendar snapshot replaces cached rows in a transaction. A failed fetch leaves the prior cache available.

## Identity and event time

Local, Google and Moodle events retain different source identities even when titles match. Provider identities include the source account/feed, calendar, upstream event UID/ID and recurrence instance. Recurring local occurrences link back to their saved series. Completion and reminders use occurrence identities, so one completed deadline does not complete every occurrence in its series.

Dates and datetimes are ISO strings. An all-day event uses date-only boundaries with an **exclusive** end date: 2026-10-30 through 2026-10-31 occupies October 30. Timed values preserve timezone/offset information and are converted for display in the selected IANA timezone. `Event.timezone` preserves a local recurring series' wall-clock timezone through daylight-saving changes. All-day dates stay calendar dates rather than being shifted through UTC. Monthly recurrence skips a month when its original day does not exist, so a January 31 series does not produce a February 28 occurrence. Recurring local wall times skipped by a spring clock change are omitted, and reminder offsets/snoozes use elapsed UTC minutes across clock changes.

The optional visual deduplication setting only suppresses equivalent entries in a view; it does not delete source data or merge event identities. Keep it disabled when comparing two independently managed calendars with similar events.

## Polling and offline state

Google uses paginated event queries over a bounded, configurable time window with recurring instances expanded by the API. The default window is 30 days in the past and 180 days ahead. The current implementation does not store incremental sync tokens. A new successful snapshot reconciles changes and removals inside the fetched window, and each account/calendar is scoped independently.

Moodle URLs define the maximum exported date range and event selection. The app downloads and validates an authoritative ICS snapshot, expands recurring occurrences for its configured window and replaces that feed's event cache after success. It cannot recover history that the feed does not export. Downloads are limited to 5 MiB after decompression, three HTTPS redirects, 10,000 VEVENT components and 20,000 expanded occurrences.

Polling occurs on startup, at the configured interval while running and on explicit refresh. Connectivity failures do not invalidate local tasks or erase existing external caches. Per-source state records the last successful synchronization and the current error/reconnection condition. A later poll retries. There is no remote write queue because online sources are read-only.

## Credentials and trust boundaries

The credential service stores serialized Google OAuth credentials and full Moodle subscription URLs in the operating system's credential store, referenced by opaque keys in SQLite. No plaintext fallback is supplied. Local-only use remains possible if credential storage is unavailable.

The app owner supplies one Google Desktop OAuth client for a build. Configuration lookup checks `UNIFIED_SCHEDULER_GOOGLE_CLIENT_CONFIG`, the bundled `unified_scheduler/resources/google-oauth-client.json`, the source checkout's `local-config/google-oauth-client.json` (only when running from source), then the legacy `google_client_config` setting. The selected configuration must be a valid Desktop client with Google's authorization/token endpoints. An invalid selected file fails without falling through to a different client. Users start browser authorization through Connect or Reconnect; there is no configuration picker in the UI.

The build validates and copies only the required Desktop OAuth fields into its application resources. This installed-app client identifies the application and is recoverable from the distribution; it does not authenticate any user by itself. PKCE, state handling and nonce/verified-identity checks protect individual authorization attempts. Account tokens remain separate in the credential vault, and token renewal uses the client information already stored with each authorized account. No OAuth token or personal calendar data is part of the packaged application.

New Google authorizations request `openid`, `userinfo.email`, `calendar.calendarlist.readonly` and `calendar.events.readonly` (full Google scope URLs are defined in `providers/google.py`). Calendar listing and event reads are the only Calendar API operations. Both Calendar permissions must be granted; an explicit empty or partial grant is rejected. Existing `calendar.readonly` grants remain usable to avoid breaking saved accounts; removing a historical broader grant requires the user to revoke it in Google and authorize again. Account identity verification is distinct from Google approving the application itself.

The vault service namespace includes a hash of the data-directory path. Long credentials use bounded chunks and a generation manifest to respect Windows generic-credential blob limits. A new manifest is committed only after all chunks are written; failed updates retain the prior complete generation. Moving a data directory changes the namespace, so sources must be reconnected after such a move.

Calendar text is untrusted content and displayed as text. Calendar links require an explicit user action. Provider transport uses certificate validation, timeouts and bounded payloads. Error strings crossing into persistent status/UI must not contain private URLs or token material. Tests use injected fake credentials rather than the real user's vault.

SQLite contains personal event titles, descriptions, locations and account metadata. It is not encrypted by this application. Credentials belong in the vault, but the calendar database and its backups still require normal user-profile and device protection.

## Schema versioning and maintenance

`database.py` is the authoritative schema definition. Schema version **2** is tracked with `PRAGMA user_version`; the version 1 upgrade transaction adds occurrence ownership records. The repository initializes an empty database and checks its schema version before use. Transactions keep related updates consistent; parameters carry user values rather than SQL string interpolation.

| Table | Stored data |
| --- | --- |
| `source_accounts` | Source kind, display label, verified identity, opaque credential reference, sync status/error and last success |
| `calendars` | Account ownership, remote calendar identity, name, color and visibility |
| `local_tasks` | Local event/task dataclass payload plus indexed identity and date fields |
| `cached_events` | External occurrence payloads indexed by account, calendar and start |
| `local_completion_status` | Per-occurrence personal completion state |
| `reminder_state` | Reminder configuration, delivered/dismissed state and snooze time |
| `app_settings` | JSON-encoded non-secret application preferences |
| `event_ownership` | Retained occurrence ownership for deleting tracking state when sources are removed, including IDs outside a rolling cache window |

The database uses WAL journaling. Sync state belongs to `source_accounts`; a separate sync-token table is unnecessary for full polling. The retained ownership table prevents a disconnected source from leaving orphaned completion or reminder state.

Do not manually copy a live WAL database's main file alone. Close the app before copying its data directory, or use SQLite's backup API. A database restore does not restore Windows Credential Manager contents; reconnect sources if their vault entries are unavailable. Newer schema versions should be migrated deliberately with a backup, never silently reset.

## Delivery boundaries

The application relies on the running Windows process and Qt tray support for reminders. All-day reminders are anchored at 09:00 in the display timezone before applying the configured offset. Old appointment reminders expire after 24 hours; incomplete tasks can receive one overdue reminder, while recurring task instances more than a day old are skipped to avoid a backlog burst. Delivery is persisted before the UI shows a notification, favoring duplicate prevention if the process exits during delivery.

No Windows service or Task Scheduler reminder process is installed. The optional startup setting launches the normal application at user sign-in. The PyInstaller configuration produces a portable folder containing a Windows executable, its runtime dependencies and an optional app-owned Desktop OAuth configuration; it does not provision online accounts or package user credentials.
