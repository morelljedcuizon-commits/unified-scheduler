# Unified Scheduler

A native Windows desktop calendar and task manager built with Python, PySide6 and SQLite. Today brings local tasks, Google Calendar events and Moodle deadlines into one view. Local planning works without an account, internet connection, backend or paid service.

## Run from source

Use 64-bit Python **3.12 or newer** on Windows. In PowerShell, from this folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unified_scheduler
```

The first-launch screen offers Google, Moodle or a local-only workspace. Google requires your own legitimate Desktop OAuth client configuration; Moodle requires a private calendar export URL. Neither is needed to start the app.

Inspect a populated workspace without accounts:

```powershell
.\.venv\Scripts\python.exe -m unified_scheduler --demo
```

Demo mode uses a separate temporary database, labels sample calendars clearly and disables network connections. Quitting the app discards its sample edits. It does not seed your real calendar.

Use **Quit** in the tray menu to exit completely; with minimize-to-tray enabled, the window's close button keeps reminders running. Keyboard shortcuts: **Ctrl+N** adds a task, **Ctrl+F** focuses search and **F5** refreshes calendars.

An alternate data directory is useful for development:

```powershell
.\.venv\Scripts\python.exe -m unified_scheduler --data-dir .\local-config\scratch
```

## What is included

- Today dashboard with overdue tasks, all-day items, chronological events, upcoming items and completion counts.
- Day, week, month and agenda views (month view is the default); a mini-calendar; title/description search and source visibility controls.
- Local task/event creation, editing and deletion, priorities, status, all-day dates, locations, daily/weekly/monthly recurrence and reminders.
- Multiple Google accounts with browser-based authorization, read-only Calendar access and independent caches.
- Multiple Moodle HTTPS calendar subscriptions with recurrence expansion and private URLs in the OS credential store.
- Offline event cache, automatic and manual background synchronization, per-source sync status and error reporting.
- Local completion tracking for imported events, reminder snooze/dismiss, Windows tray notifications and an optional minimize-to-tray mode.
- Light/dark appearance, configurable display timezone, reminder defaults, sync window/frequency and optional Windows startup.

Google and Moodle are read-only in this release. Marking an imported deadline complete records a personal tracking state; it does not submit coursework or change the remote event. Local events are never copied to an external calendar.

## Google setup

1. Create or select a Google Cloud project and enable the **Google Calendar API**.
2. Under **Google Auth platform → Branding**, supply the application's name, support email and contact information.
3. In **Audience**, choose **External** when accounts outside your Workspace organization will use the app. While publishing status is Testing, add every intended account under **Test users**.
4. Under **Data Access**, configure the requested scopes: `openid`, `https://www.googleapis.com/auth/userinfo.email`, and `https://www.googleapis.com/auth/calendar.readonly`. Review Google's verification requirements before distributing the app publicly.
5. Under **Clients**, create an OAuth client with application type **Desktop app**. Download its JSON configuration and keep it outside source control.
6. In Unified Scheduler, choose **Connect Google Account**, select that JSON configuration and complete Google's consent screen in your system browser. Repeat to connect another account.

These steps follow Google's [Calendar Python quickstart](https://developers.google.com/workspace/calendar/api/quickstart/python) and [OAuth consent configuration guide](https://developers.google.com/workspace/guides/configure-oauth-consent). The Cloud console may update its labels over time.

The app uses an authorization-code flow with PKCE and a loopback redirect on `127.0.0.1`. Your Google password is entered only on Google's page. A desktop client configuration identifies the application; user access/refresh tokens are stored separately in Windows Credential Manager. See Google's [desktop authorization documentation](https://developers.google.com/identity/protocols/oauth2/native-app).

For an External app in Testing, Google generally issues refresh tokens that expire after seven days when Calendar scopes are requested. Revocation, organization policy and token limits can also require reconnection. Publishing and scope verification depend on the app's audience and use case; an unverified personal testing project is not a verified public product. See [Google's token expiration guidance](https://developers.google.com/identity/protocols/oauth2#expiration).

Use the Accounts page to choose calendars and reconnect or disconnect an individual account. Disconnect removes that account's local credentials and cached events; it does not delete anything in Google. You can also revoke access in your Google account's third-party connections settings.

## Moodle / MSU-IIT MOLE setup

1. Sign into your Moodle site in a browser and open its calendar.
2. Select **Export calendar**. Choose **All events** if you want the academic events your account can access, then choose an appropriate time range.
3. Choose **My personal events** and the **Recent and next 60 days** time period, then select **Get calendar URL / Get URL address** and copy the generated HTTPS URL.
4. In Unified Scheduler, choose **Add Moodle Calendar**, enter a display name and the URL, then use **Test Connection** and **Save**.

A URL with `preset_what=user` includes only personal events. `preset_time=recentupcoming` is a moving recent/upcoming window, not unlimited history. Course permissions, export choices and the Moodle installation determine what is returned. Consult [Moodle's calendar export documentation](https://docs.moodle.org/en/Using_Calendar).

The app never needs a Moodle username or password. The private URL acts like a credential: do not paste it into issue reports, screenshots or a repository. If it expires, generate a replacement and use **Edit Calendar**. Accounts also offers refresh, hide/disable and remove actions. Hiding a calendar preserves its cache; removing its source deletes the cache and stored URL.

The downloader validates TLS certificates, permits only HTTPS redirects, limits downloaded content and rejects login pages/invalid ICS. Errors are presented without revealing the private URL. A calendar may sync successfully with zero entries if its export window contains no events.

## Reminders, tray and offline behavior

Reminders default to 30 minutes before an event. Change the default in Settings or configure an individual occurrence in its details, including Off. All-day reminders use 09:00 in the selected display timezone before applying the offset. Completion, dismissal and snooze state persist across launches. Notifications use Qt's Windows system-tray notification support; Windows notification settings, Do Not Disturb and session state can affect their display.

**The process must remain running for reminders and polling.** Minimize to tray keeps it running. Choosing Quit or terminating the process stops notifications. Optional Windows startup is disabled initially and starts the app at user sign-in; it is not a background service or an OS reminder scheduler.

When a sync fails, its previous cache remains available and the source status shows the problem. Local changes continue to save in SQLite. Periodic sync retries while the app is running. Cached events can be incomplete outside the configured sync window, and Moodle's own exported range can be narrower still.

## Storage and privacy

By default, Qt's per-user `AppLocalDataLocation` holds `scheduler.sqlite3`; on Windows this is normally:

```text
%LOCALAPPDATA%\UnifiedScheduler\Unified Scheduler\scheduler.sqlite3
```

`--data-dir` overrides the directory. Normal and demo workspaces are separate. Windows users have separate app-data directories and credential stores.

Each data directory also has its own credential-vault namespace, so two explicit workspaces do not overwrite each other's connected-account tokens. Moving a database to another path requires reconnecting its sources. A workspace lock prevents two app instances from modifying the same database simultaneously.

SQLite contains local tasks, source/calendar metadata, external event caches, completion state, reminder state and settings. It does **not** store Google tokens or full private Moodle subscription URLs. Those are stored through `keyring` in Windows Credential Manager under opaque references. There is no plaintext credential fallback. The database still contains personal calendar content: protect it with your Windows account and device security, and do not commit it.

Back up a closed application's data directory to retain local tasks and settings. Restoring the database on another Windows account or computer does not transfer the credential vault; reconnect Google accounts and replace Moodle URLs there. See [architecture and schema](docs/architecture.md) for implementation details.

## Tests and manual verification

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m unified_scheduler --demo --smoke-test
Remove-Item Env:\QT_QPA_PLATFORM
```

Automated tests use temporary databases and mocked providers rather than private accounts. Live Google consent/token renewal, private Moodle exports, desktop notification delivery and sign-in startup need verification in the user's Windows session. Follow [the manual verification checklist](docs/manual-verification.md); a successful mocked test is not evidence that a particular real account or feed works.

See [the implementation verification report](docs/verification.md) for the checks completed on this build.

## Build a Windows executable

Build on Windows with the same Python architecture as the target machine:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build.ps1
```

The script installs development/build dependencies, runs tests and uses `UnifiedScheduler.spec`. To reuse an already installed environment, add `-SkipInstall`.

Direct build:

```powershell
$env:PYINSTALLER_CONFIG_DIR = Join-Path $PWD '.build-cache'
.\.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm .\UnifiedScheduler.spec
```

Run `dist\UnifiedScheduler\UnifiedScheduler.exe`. Distribute the **entire** `dist\UnifiedScheduler` directory, including `_internal`; the executable depends on those files. This is a windowed portable folder build, not an installer. The spec bundles Qt, timezone data and Google discovery data. See [PyInstaller's usage guide](https://pyinstaller.org/en/stable/usage.html).

No private OAuth configuration, database, Moodle URL or token is bundled. Production distribution should add your release signing and installer/update process as appropriate. A self-built executable is not code-signed by this project.

## Project layout

```text
src/unified_scheduler/
    __main__.py       Application entry point and command-line options
    models.py        Shared account, calendar and occurrence models
    database.py      Versioned SQLite repository
    aggregation.py   Unified queries and local recurrence
    timeutils.py     Timezone and all-day helpers
    credentials.py   OS credential storage
    reminders.py     Persistent reminder eligibility and state
    sync.py          Provider coordination and sync windows
    demo.py          Isolated sample workspace
    providers/       Google OAuth/Calendar and Moodle ICS
    ui/              Native Qt windows, views, dialogs and styles
tests/               Offline automated verification
docs/                Architecture and live verification guidance
scripts/build.ps1    Windows build helper
UnifiedScheduler.spec
```

## Release boundaries

This release uses reliable full-window polling rather than incremental sync tokens or push notifications. Each successful calendar fetch replaces that calendar's cache; failed fetches retain previous data. This avoids combining unsupported incremental query parameters; Google's [incremental sync guide](https://developers.google.com/workspace/calendar/api/guides/sync) describes the alternative protocol.

Google event writing, two-way Moodle synchronization, a terminated-process reminder service, an installer, code signing and automatic updates are outside this release. Local recurring events support daily, weekly and monthly repetition; edits operate on the local series, while completion/reminders can be tracked per occurrence. Calendar cache contents are constrained by provider access and configured/exported dates.
