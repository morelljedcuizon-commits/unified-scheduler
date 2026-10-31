# Public release implementation audit

Audit date: October 30, 2026. This describes the existing Python/PySide6 Windows desktop application and the incremental release preparation in this checkout. It does not certify a Google Cloud project, a public release, or Google verification.

October 31 update: the developer confirmed the API works and testing is complete. Source changes were committed and pushed; public contacts and policies were finalized, and the [website was deployed to GitHub Pages](PUBLIC_SITE.md#published-website). Hosting and initial policy finalization mentioned as remaining below describe the October 30 audit state. No custom domain or Google verification outcome is claimed.

The audit began before the public-release changes. The checkout already contained the earlier app-owned OAuth configuration change and 96 passing tests. Those changes were retained. The last reported Cloud setting is **External / Testing**; the repository cannot establish the live Console state.

## Existing behavior and necessary changes

| Area | Already implemented at audit start | Release preparation or remaining action |
| --- | --- | --- |
| OAuth initialization | `providers/google.py` creates an `InstalledAppFlow`, uses an authorization code with PKCE, opens the system browser, and receives a loopback callback on `127.0.0.1` with an ephemeral port. | Preserve this flow. No embedded Google password form or hosted OAuth backend is needed. |
| Client configuration | `google_oauth.py` already resolves an app-owned Desktop client from an explicit environment override, bundled resource, source-only developer file, or legacy saved path. Connect and Reconnect no longer show a file picker. | Supply a legitimate Desktop client for the correct Cloud project before a Google-enabled release. Invalid selected files fail safely; missing configuration leaves local use available. |
| Identity and multiple accounts | Google verifies the signed ID token with the client ID audience. The provider checks `sub`, verified email and nonce; stable account IDs derive from `sub`. Each account has separate vault keys, calendars and cached event identities. Reconnect rejects a different account. | Preserve identity verification and account isolation; add an end-to-end mocked two-account connection/disconnection regression. |
| OAuth permissions | The initial implementation requested `openid`, `userinfo.email` and the broad read-only Calendar scope. It only calls Calendar list and event-list methods. | New authorizations now request `calendar.calendarlist.readonly` and `calendar.events.readonly`, plus identity scopes. Existing broad read-only grants remain usable. Declare the exact requested scopes in Cloud Console and the verification submission. No Calendar writes are introduced. |
| User token storage | Access/refresh tokens are serialized into `CredentialStore`, which uses Windows Credential Manager. SQLite stores only opaque credential references. Large credentials are split into bounded chunks with atomic manifest replacement; there is no plaintext fallback. | Preserve the vault implementation. A Desktop client configuration may be distributed; user authorization tokens must never be included. |
| Workspace isolation | `__main__.py` derives a credential service namespace from the resolved workspace directory. Separate Windows accounts also have separate OS stores. | Added a mocked namespace regression proving that deleting one workspace's chunked credential does not affect the same account key in another workspace. Moving a data directory still requires reconnection. |
| Expiration and revocation | The provider refreshes expired access tokens from the vault. Missing, invalid, expired or revoked refresh credentials become `reauthenticate`; transient transport failures become offline states. Cached events remain. | Preserve automatic refresh. Existing Accounts controls provide reconnection; production removes only the special Testing lifetime for new authorizations, not all possible future revocation. |
| Authorization errors | Provider errors use deliberately sanitized messages; callback logging is disabled. Network work runs in Qt workers. Failure does not create a new connected account. | Retain sanitization and actionable retry/reconnect guidance. Console restrictions cannot be bypassed by local error handling. |
| Calendar synchronization | Paginated read-only full-window polling expands recurring events, stages a successful account snapshot before reconciliation, retains caches on failures, and isolates accounts. | Preserve polling and cache behavior. Incremental tokens, push delivery, two-way sync and Google event writing are outside this preparation. |
| Disconnect | Removes the selected account's vault credentials, cached events and associated completion/reminder metadata. Other accounts, Moodle subscriptions and local tasks remain. | Added regression coverage for these boundaries. Disconnect does **not** revoke the remote Google grant; users can revoke it in Google Account connections. |
| Local and Moodle use | No Google account is required. Local tasks, reminders, offline caches, multiple Moodle HTTPS feeds, source controls and demo mode already work. | Preserve all features. The earlier shared Moodle sync-window repair is retained and covered by existing regression tests. |
| Per-user data and onboarding | Qt chooses the per-user application data directory, SQLite initializes itself, first launch offers local/Google/Moodle, and a workspace lock prevents simultaneous database modification. | Preserve defaults and test the packaged first-launch experience on a clean Windows account. |
| Windows packaging | PyInstaller already bundles Qt, Google discovery data, timezone data, the Windows credential backend and the icon resource. The earlier change bundles only sanitized Desktop OAuth fields when configured. | Embed the icon in the executable as well as the UI; prepare a repeatable release build and artifact checks. The portable folder must include `_internal`. |
| Public presence | MIT license, README, architecture, verification and manual checklists exist. No public privacy/terms site or OAuth publication guide existed at audit start. | Add `docs/public-site`, publication and release guides, and manual deployment/build workflows. Hosting, domain ownership and verification remain owner actions. |

## Data and trust boundaries

The desktop process talks directly to Google and the configured Moodle HTTPS calendar endpoint. The audited application has no developer-operated calendar server, analytics collector, or event-upload endpoint. That is a statement about this implementation, not a guarantee about a user's network, Windows environment, Google, Moodle, or GitHub website hosting.

The local SQLite database contains personal calendar content and account metadata and is not encrypted by this application. Windows Credential Manager protects credentials separately. Demo screenshots and automated tests use synthetic data; they are not evidence of authorization with a real Google account.

Secrets and repository history were reviewed separately in [SECURITY_REVIEW.md](SECURITY_REVIEW.md). Preserve the existing [MIT license](../LICENSE) and include it in distributions.

## Completion boundaries

| State | Evidence or action |
| --- | --- |
| Implemented and tested | App-owned configuration, browser OAuth mechanics with mocked identity responses, account/cache/vault isolation, automatic refresh and reauthentication handling, local/Moodle/task regressions. See [verification.md](verification.md) for the final test count and build results. |
| Implemented but requires manual testing | Real consent and loopback callback, fresh-user access outside the old test list, scope transition, production reauthorization, vault writes in a normal Windows session, and clean-machine packaged operation. Follow [manual-verification.md](manual-verification.md). |
| Requires developer configuration | Confirm the actual Cloud project/status, provide its Desktop client, finalize public contact and policy text, choose and verify an owned domain, deploy the public site, configure Branding/Audience/Data Access, and deliberately publish a Windows release. |
| Requires Google approval | Branding and applicable sensitive-scope verification. Publishing status and verification approval are separate. Neither this audit nor a local build proves approval. |

The owner-facing sequence is in [GOOGLE_OAUTH_PUBLICATION.md](GOOGLE_OAUTH_PUBLICATION.md). The target remains an appropriately published and verified application; no verification result is inferred from source code.
