# Implementation verification

Verified on October 30, 2026, using Windows 11, Python 3.14.7, PySide6/Qt 6.12.0 and PyInstaller 6.22.3.

Website validation was completed on October 31, 2026. The app/package results below remain the completed October 30 run; no real provider credentials were used.

The developer subsequently confirmed that the API works and testing is complete, and authorized website publication on October 31. Live provider tests below describe the limits of this agent's earlier checks, not a request to repeat the developer's completed testing. The website draft notices have now been removed for publication.

## Completed checks

- **114 pytest tests pass** in the complete suite (29.59 seconds). Coverage includes local CRUD, recurrence, all-day exclusive ends, daylight-saving transitions, multi-account isolation, authoritative event replacement/deletion, offline cache retention, calendar filters, OAuth PKCE/identity/nonce checks with mocks, token renewal/reauthentication, ICS payload/URL confidentiality, reminders/deduplication/snooze and GUI interactions.
- Google Connect/Reconnect starts without a JSON picker and triggers initial background sync in mocked Qt integration tests. Tests also cover app-owned configuration lookup, frozen resource paths independent of the working directory, invalid configurations, denied Calendar permissions and protection of the original account/cache when reconnecting as another user.
- The build specification was exercised with synthetic Desktop configuration: only required client fields are staged, the explicit override wins, invalid selected files fail, and missing configuration produces a local/Moodle-only build. No real OAuth configuration was supplied or bundled for this verification.
- New scope tests require both narrow Calendar permissions, reject explicit empty/partial grants and sanitize consent-denial errors. A legacy broader read-only grant remains usable. Lifecycle tests exercise two Google accounts, disconnect isolation, revoked-token cache retention and workspace credential namespaces.
- Nine release-packaging regressions exercise the actual spec with stubbed PyInstaller constructors and inspect synthetic distribution folders. They check the icon, normalized client resource, broken-override failure, stale-config exclusion, build-manifest consistency and rejection of common private/development files.
- Restored the shared sync-window helper already referenced by Moodle's connection dialog. All three existing connection/sync regression tests pass.
- Source application starts without online credentials in an empty local workspace and in the isolated demo workspace.
- Native Windows and offscreen Qt smoke checks exercise all six navigation pages and the day/week/month/agenda views. The extended smoke path also loads Google's packaged Calendar discovery document, parses a sample ICS calendar and imports the Windows credential backend without network access.
- Visual inspection at 1366×768 covered Today, month view, light/dark themes and the scrollable task editor. A 1000×650 window was also exercised; details collapse until requested. Demo previews are in `artifacts/`.
- Windows Credential Manager successfully stored, retrieved and removed a synthetic non-secret value large enough to exercise credential chunking. This used a unique temporary service namespace and left no test credential behind. The sandbox's restricted logon session cannot write to the vault; the native user session can.
- `pip check` reports no broken dependencies.
- `scripts/release.ps1 -SkipInstall -AllowLocalOnly` completed: tests, isolated PyInstaller build, frozen demo smoke, artifact content inspection, ZIP and SHA-256 receipt. The generated candidate is `dist/candidate-20261030-145218-15b37fdf/UnifiedScheduler-1.0.0-windows-x64-local-moodle.zip` (72.7 MiB). It includes 1,450 files; ZIP integrity, checksum and an exact folder-to-archive file comparison passed. The PE executable contains its icon resource. No GitHub Release was created.
- The [security review](SECURITY_REVIEW.md) inspected all three commits reachable from available local refs, plus the initial working snapshot. No confirmed live secret or private calendar/database was found; the review documents its limits.
- Website checks validated three HTML pages, 70 links/assets, internal anchors, image alternatives, viewport declarations and local documentation links. The local HTTP preview returned success. Edge screenshots were inspected at 1440px desktop width and 540px narrow width for the homepage/privacy/terms. A formatting defect in CSS pseudo-selectors was corrected. The 390px CLI capture cropped Edge's minimum-width viewport, and remote mobile emulation was unavailable; actual phone/390px rendering and keyboard interaction remain manual checks. Successful previews are in `artifacts/public-site-desktop.png` and `artifacts/public-site-*-narrow.png`.
- The website uses the developer-supplied publisher name and contact email. Its two application screenshots were visually inspected and show the explicit isolated DEMO workspace and synthetic sample events. Privacy/terms were initially marked for review, then finalized for the developer-authorized October 31 publication. The manual Pages workflow rejects future draft notices. The Windows candidate workflow has not been run on GitHub.

## Checks requiring user accounts or an interactive Windows session

Actual Google authorization, real account calendars, revoked consent and token expiry must still be tested with the developer's legitimate Desktop OAuth client and allowed Google users. Private Moodle subscriptions require user-supplied URLs. No real Google account or Moodle feed was authorized during development.

The current ZIP is deliberately **local/Moodle-only** because no real Desktop OAuth client was supplied. It does not prove a Google-enabled frozen login. The manual Windows/GitHub Actions workflow was prepared but not run in GitHub; its Windows/Python 3.12 runner remains an external check. Google Cloud was last reported as External / Testing and was not accessed. No Production switch, domain verification, branding approval or sensitive-scope approval is claimed.

Notification display can be suppressed by Windows settings; end-to-end notification delivery and sign-in startup have not been manually verified. Startup registry command generation is covered by a mock test and does not enable startup during tests. A clean-machine run without the development environment and high-DPI scaling checks remain part of the [manual verification checklist](manual-verification.md).

Google and Moodle are read-only. Notifications require the app to remain running. The executable is an unsigned portable folder build; distribute its entire folder rather than the `.exe` alone.
