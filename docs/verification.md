# Implementation verification

Verified on October 30, 2026, using Windows 11, Python 3.14.7, PySide6/Qt 6.12.0 and PyInstaller 6.22.3.

## Completed checks

- **67 pytest tests pass.** Coverage includes local CRUD, recurrence, all-day exclusive ends, daylight-saving transitions, multi-account isolation, authoritative event replacement/deletion, offline cache retention, calendar filters, OAuth PKCE/identity/nonce checks with mocks, token renewal/reauthentication, ICS payload/URL confidentiality, reminders/deduplication/snooze and GUI interactions.
- Source application starts without online credentials in an empty local workspace and in the isolated demo workspace.
- Native Windows and offscreen Qt smoke checks exercise all six navigation pages and the day/week/month/agenda views. The extended smoke path also loads Google's packaged Calendar discovery document, parses a sample ICS calendar and imports the Windows credential backend without network access.
- Visual inspection at 1366×768 covered Today, month view, light/dark themes and the scrollable task editor. A 1000×650 window was also exercised; details collapse until requested. Demo previews are in `artifacts/`.
- Windows Credential Manager successfully stored, retrieved and removed a synthetic non-secret value large enough to exercise credential chunking. This used a unique temporary service namespace and left no test credential behind. The sandbox's restricted logon session cannot write to the vault; the native user session can.
- `pip check` reports no broken dependencies.
- PyInstaller successfully produces `dist/UnifiedScheduler/UnifiedScheduler.exe` and its adjacent runtime directory. Frozen GUI smoke checks exit with code 0.

## Checks requiring user accounts or an interactive Windows session

Actual Google authorization, real account calendars, revoked consent and token expiry must still be tested with the developer's legitimate Desktop OAuth client and allowed Google users. Private Moodle subscriptions require user-supplied URLs. No real Google account or Moodle feed was authorized during development.

Notification display can be suppressed by Windows settings; end-to-end notification delivery and sign-in startup have not been manually verified. Startup registry command generation is covered by a mock test and does not enable startup during tests. A clean-machine run without the development environment and high-DPI scaling checks remain part of the [manual verification checklist](manual-verification.md).

Google and Moodle are read-only. Notifications require the app to remain running. The executable is an unsigned portable folder build; distribute its entire folder rather than the `.exe` alone.
