# Manual verification on Windows

Use test calendars and harmless sample tasks. Do not put private URLs, access tokens, refresh tokens or account credentials in screenshots or bug reports. Automated provider tests use mocks; these checks exercise the actual browser, network, credential vault and Windows session.

## Local workspace and interface

1. Start `python -m unified_scheduler --data-dir .\local-config\verification` and choose local-only setup.
2. Add a task due today, a task due yesterday, a future event and an all-day item. Include descriptions, a location, different priorities and a recurrence.
3. Check Today, Tasks, Upcoming and day/week/month/agenda views. The overdue task should be identifiable, the all-day item should not appear as a timed appointment, and completion should update task counts.
4. Edit a task and restart the process. Its edits and completion should remain. Delete it and restart again; it should stay deleted.
5. Search for a word that appears only in a description. Filter by source/calendar and navigate to another date with the mini-calendar and Today control.
6. Try light/dark themes, a small window, 1366×768 and 1920×1080 displays, and Windows 125%/150% scaling. Check keyboard tab order and that form buttons remain reachable.
7. Run `python -m unified_scheduler --demo`. Verify the demo label is prominent and the normal workspace remains unchanged after the demo closes.

## Google consent and multi-account isolation

1. Complete the README's Google Cloud setup with an External Desktop OAuth client and two allowed test accounts.
2. Connect the first account. Confirm the system browser opens Google's account chooser and read-only Calendar consent. Complete consent and return to the app.
3. Connect the second account. Check both verified identities and their calendars appear independently.
4. Create events with the same title in both accounts. Sync repeatedly. Both should remain, with their own source/calendar identities, and neither should multiply.
5. Hide one calendar. Its events should disappear from views without disconnecting the account. Show it again.
6. Change an event's date in Google, delete another, and cancel one occurrence of a recurring series. Sync and check the old time/deleted/cancelled occurrences disappear within the fetched window.
7. Test a calendar with enough events to require pagination and a recurring event spanning a daylight-saving change in another timezone. Compare displayed instants with Google Calendar.
8. Close and reopen after the access token expires; synchronization should refresh authorized credentials without a token file appearing in the workspace.
9. Revoke this app from one Google account's third-party access settings. Sync, confirm reconnection is requested and cached items remain available. Reconnect the same account.
10. Disconnect one account. Verify its local cached events disappear while the other account remains intact. Confirm the remote Google events were not deleted.

## Moodle feeds

1. Export a private HTTPS calendar URL with All events and the desired date range. Add it using a non-secret display name and Test Connection.
2. Add a second feed from a different account or installation. Sync several times and verify stable counts and independent source labels.
3. Compare a known assignment deadline, quiz and all-day calendar entry against the Moodle page. Check the selected display timezone.
4. If you can edit the source calendar, change or remove an event, then sync. The authoritative update should replace its cached predecessor without creating duplicates.
5. Edit a feed to use an invalid or expired URL. Check the error is understandable, the private URL/token is absent from the message, and previously cached events remain visible.
6. Test an HTTPS login page that returns HTML instead of ICS and a URL using `http://`. Both should be rejected with an actionable message.
7. Hide and show one feed, then remove it. Verify the other feed remains. A removed feed should have neither cached events nor its credential-vault entry.
8. Inspect `scheduler.sqlite3` using a SQLite tool: the full subscription URL and its `authtoken` value must not be stored there. Do not copy the database into public reports: its event data is personal.

## Offline and reminder behavior

1. With successful caches in place, disconnect the network and press Sync. The UI should remain responsive, local tasks editable and cached items visible with failed/stale sync information.
2. Restore the network. Manual or periodic sync should recover without duplicating events or overwriting local task edits.
3. Create an event a few minutes ahead with an at-time reminder. Keep the app running and allow notifications in Windows settings.
4. Confirm one notification appears. Keep the app open for several reminder checks and restart it: the same reminder should not repeatedly notify.
5. Configure another reminder, snooze it and verify the new delivery time. Dismiss a reminder and complete another task before its reminder is due; both should remain suppressed as appropriate.
6. Enable minimize to tray. Close/minimize the window according to the UI option and verify the process remains in the tray and can be reopened. Test reminder delivery while hidden.
7. Quit from the tray. Confirm the process exits. No reminder delivery is expected while the app is fully terminated.
8. Enable Start with Windows, sign out and sign in, then confirm the app opens. Disable the setting and verify the startup entry is removed. Do this in a test user session before relying on it.

## Packaged build

1. Run `scripts\build.ps1` and copy the entire `dist\UnifiedScheduler` folder to a test location.
2. Run `UnifiedScheduler.exe --demo --smoke-test`; it should open briefly and exit successfully without missing-module errors.
3. Run the executable normally on a Windows account without the development Python environment. Repeat a local save/restart, credential-vault connection and tray reminder check.
4. Verify the distribution contains no personal database, OAuth client configuration or secret token files. Public releases need a deliberate signing/distribution process; this project does not supply one.

Record the app version, Windows version, Python/Qt version for source runs, test date, scenario and result. Use redacted descriptions of failures and keep account/feed values private.

