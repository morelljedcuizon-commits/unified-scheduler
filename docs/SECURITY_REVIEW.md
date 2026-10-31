# Repository and history security review

Reviewed October 30, 2026. No confirmed live user token, authorization code, private Moodle subscription, personal calendar export, local database, or private key was found in the inspected repository snapshot. This is a bounded source/history review, not a claim that secrets can never have existed elsewhere.

## Scope and method

- Inspected all **3 commits reachable from locally available Git refs**, including the remote-tracking ref available in this checkout. The examined history contains **39 unique blobs across 39 paths**, of which **38 are text**; the remaining blob is the application icon.
- Scanned **42 tracked and non-ignored working-tree files at the initial audit snapshot**, including the earlier uncommitted OAuth changes. A follow-up pass over **58 working-tree files** during release preparation found no recognizable live Google credential/private-key/callback-code format or database/export/key file. That later snapshot includes the owner's intentionally public contact details and four image/icon files; pattern scanning alone cannot establish an image's privacy.
- Enumerated each reachable commit's complete tree, read each unique blob without executing it, and looked for recognizable Google access/refresh token formats, client-secret formats, private-key headers, OAuth callback codes, literal token assignments, credential-bearing Moodle URLs, email addresses, database signatures, and export/key file extensions.
- Examined candidate context to distinguish synthetic tests/demo content from credentials. Reports print only category, file, line number and commit identifier; no matched credential values are reproduced here.
- Used `git ls-files --cached --others --exclude-standard` for working files. Ignored local configuration, build output, virtual environments, personal databases, Windows Credential Manager, and user account data were not opened as part of this repository audit.

No new fetch or scan of deleted GitHub branches, forks, release assets, Actions artifacts/logs, unreachable Git objects, reflogs, developer backups, or other machines was performed. Those are outside the available-history claim. Pattern searches can miss unusual encodings or unknown secret formats; manual review and ongoing secret scanning remain useful.

## Candidate review

The populated historical tree appears in commits `da96d39` and `b524e27`; the earlier `260ed17` commit was included in the traversal.

| Location in historical tree | Candidate type | Review result |
| --- | --- | --- |
| `tests/test_core.py:251` | Literal token-like fixture | Synthetic long strings used to test credential chunking; not live Google credentials. |
| `tests/test_providers.py:129`, `:131`, `:139`, `:151`, `:172`, `:333` | Moodle URL query credentials | Example-domain URLs and deliberate synthetic markers used for sanitization/privacy tests; not real private subscriptions. |
| `tests/test_providers.py:259`, `:272`, `:296`, `:302`, `:303` | Access/refresh/client/identity fixture values | Synthetic mock credentials and a test client identity; no matching live Google token or client-secret format detected. |
| `tests/test_providers.py:120`, `:200`, `:310`, `:314` | Account-like addresses | Example test identities. |
| `tests/test_sync_ui_regression.py:76`, `:136` | Moodle query credentials | Synthetic integration-test URLs; network calls are mocked. |
| `src/unified_scheduler/demo.py:19` | Account-like address | Explicitly labeled demo identity. Demo mode uses a temporary workspace and blocks online connection. |

The earlier uncommitted `tests/test_google_oauth_config.py` and `tests/test_google_signin.py` also contain synthetic configuration/identity values and hostile placeholder inputs used to test validation. New lifecycle tests follow the same pattern. No historical `.sqlite`, `.sqlite3`, `.db`, `.ics`, private-key file, or SQLite signature was found.

Source line numbers refer to the reviewed historical versions and may move after edits. This review intentionally does not copy candidate values into documentation.

## Release controls

The existing ignore rules exclude local databases, calendar exports, token/client JSON filenames, `.env` files, `local-config`, build output and secret/key directories or extensions. Ignore rules do not remove files already committed, so history review remains necessary.

The release build must include only the validated **Desktop OAuth application identity**. This is a public client configuration, not a user's authorization. Do not bundle service-account keys, confidential Web client credentials, Google user access/refresh tokens, a developer's workspace, private Moodle URLs, or personal screenshots. Keep any build secret limited to the approved Desktop configuration and inspect the artifact before uploading it.

Review CI logs and artifact contents before publication. Keep the existing MIT license. No history rewrite, credential revocation, release publication or GitHub security-setting change was performed by this audit.

## If a future scan finds an exposure

1. Restrict further distribution and record affected file paths, commits and artifact identifiers without copying the secret into an issue.
2. Revoke compromised Google user grants/tokens, rotate an affected confidential credential as appropriate, or regenerate the private Moodle calendar URL through its provider. Deleting source text does not invalidate a credential.
3. Remove the material from current source and build inputs; inspect releases, artifacts, logs and backups that may contain it.
4. Plan a coordinated Git history cleanup with the repository owner, including affected branches/tags and copies. History rewriting can disrupt collaborators and should be deliberate.
5. Re-scan the rewritten repository and review the hosting provider's cleanup procedure. Forks, caches and previously downloaded copies may retain old material, so revocation is essential.

No rotation is recommended solely for the synthetic test candidates above.

On October 31, the website's `today-demo.png` and `calendar-demo.png` were also visually reviewed: both show the app's explicit DEMO banner and synthetic sample workspace. Browser previews use only those local public-site assets. This visual check complements, rather than expands, the bounded Git-history scan above.
