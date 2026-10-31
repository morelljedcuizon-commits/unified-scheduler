# Windows distribution and owner checklist

Prepared October 30, 2026. This prepares the existing Python/PySide6 desktop app; the static website is a separate download/information site. An artifact, source version, or GitHub upload does not prove Google Production status or verification approval.

## Build locally

Use Windows and 64-bit Python 3.12 or newer. The end user does not need Python. Install/build dependencies are declared in `pyproject.toml`; run from the repository root in PowerShell:

```powershell
# Google-enabled candidate: use your real Desktop app client, never user tokens.
powershell -ExecutionPolicy Bypass -File .\scripts\release.ps1 -GoogleClientConfig 'C:\private-config\google-oauth-client.json'

# If the owner has not supplied a client yet, explicitly prepare a local/Moodle build.
powershell -ExecutionPolicy Bypass -File .\scripts\release.ps1 -AllowLocalOnly
```

The client may instead be supplied in the ignored `local-config/google-oauth-client.json`, or by `UNIFIED_SCHEDULER_GOOGLE_CLIENT_CONFIG` pointing to an absolute file path. Only Google's `installed` Desktop client type and Google endpoints are accepted. The build stages only the required Desktop fields; neither a Web client secret nor service-account credentials are supported. A Desktop client is recoverable from the distributed program, while private user tokens stay in Windows Credential Manager. No real OAuth client is provided by the repository.

The script creates an isolated `dist/candidate-<timestamp>-<id>/` directory, runs the complete test suite, builds the portable folder with the icon and runtime assets, performs a frozen demo startup check, inspects its contents, then creates a ZIP and `.sha256` checksum. It includes `LICENSE`, `READ-ME.txt` and `build-info.json` with source revision, dirty-worktree flag and whether the client is included. `-SkipInstall` reuses an installed development environment; release checks cannot be skipped. An invalid explicitly selected OAuth configuration fails, even when local-only fallback is allowed. No Cloud Console action or GitHub publication is performed.

For a development folder without the candidate archive, use `scripts/build.ps1` as in README. `-DistPath dist\new-build` avoids a running output copy. The script checks whether that exact output executable is running before PyInstaller can replace it. Keep output inside the workspace. `--data-dir` is a runtime option, never a packaging input.

For the portable ZIP, distribute the entire `UnifiedScheduler` folder, including `_internal`. Users must **extract all files** before launching `UnifiedScheduler.exe`. Alternatively, build the installer below. Neither package has an auto-update service or code signature. Windows may show reputation/unsigned-app warnings; do not tell users to disable Windows protections. Per-user data is created on first run, outside the installation folder. See [PyInstaller's operating modes](https://pyinstaller.org/en/stable/operating-mode.html).

## Windows installer and direct website download

Install [Inno Setup](https://jrsoftware.org/isdl.php) (6.3 or newer), then build both portable and installable packages:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\release.ps1 -GoogleClientConfig 'C:\private-config\google-oauth-client.json' -BuildInstaller
```

Pass `-IsccPath 'C:\path\to\ISCC.exe'` for a compiler outside the standard installation directories. To wrap an already checked candidate without rebuilding or repeating application tests:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-installer.ps1 -AppDirectory '.\dist\candidate-<id>\UnifiedScheduler' -IsccPath 'C:\path\to\ISCC.exe'
```

The installer is `UnifiedScheduler-Setup-windows-x64.exe`, with a matching `.sha256`. It installs under `%LOCALAPPDATA%\Programs\UnifiedScheduler` without administrator access, creates a Start menu shortcut, offers an optional desktop shortcut and registers an uninstaller. New versions use the same installation identity and replace managed runtime files. Quit the app from its tray before updating. Uninstalling preserves the separate workspace and Windows credentials; use the privacy policy's removal instructions to erase personal data. A local/Moodle-only package requires `-AllowLocalOnly` and gets a distinct `-local-moodle` installer filename.

After reviewing the installer, publish a GitHub Release with the Setup executable and checksum attached. Keep the Setup asset's name constant across releases; the version is embedded in its file metadata and release tag. The website's direct-download target is:

```text
https://github.com/morelljedcuizon-commits/unified-scheduler/releases/latest/download/UnifiedScheduler-Setup-windows-x64.exe
```

That URL works only after an ordinary public release containing that exact asset exists. Drafts and prereleases do not provide the intended latest-release download. Publish the approved release first, then deploy the website button; the Pages workflow checks direct-download links before deployment. See GitHub's [release-link documentation](https://docs.github.com/en/repositories/releasing-projects-on-github/linking-to-releases).

## Build with GitHub Actions

The tracked `.github/workflows/windows-candidate.yml` has only `workflow_dispatch` and `contents: read`. It builds a candidate artifact; it has no release-publishing step or write permission.

1. Review and commit these changes to your repository's default branch. Review changes to workflows before giving them secrets.
2. In **Settings → Environments**, create `release-build`. Restrict allowed branches to your reviewed release/default branch and configure a required reviewer if available for your GitHub plan.
3. Add the environment secret `GOOGLE_DESKTOP_CLIENT_JSON` containing the valid downloaded **Desktop** client JSON. Never put an authorized-user `token.json`, personal calendar, Moodle URL or Web/service-account credential here. Treat workflow artifacts as distributable, because the Desktop client will intentionally be included in the app.
4. In **Actions → Build Windows release candidate → Run workflow**, select the reviewed branch. Keep **Include Google** enabled for a Google-enabled candidate; disable it for a clearly labeled local/Moodle-only candidate without a secret.
5. Approve the environment run if configured. Keep **Build installer** enabled to include the Setup executable. The workflow uses a Windows runner and Python 3.12 x64, runs tests/build/smoke/content checks, then uploads ZIP, installer and checksum artifacts for 14 days. The raw runner-temporary client file is removed in an `always()` step. A failed check prevents artifact upload.
6. Download and inspect the artifact. The workflow itself has not been run against this GitHub account during local preparation; its first real run remains an owner check. Dependencies use the repository's version ranges; record resolved versions and consider a reviewed lockfile before repeatable signed releases.

GitHub references: [manual workflows](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow), [environment protection](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments), [artifact upload](https://github.com/actions/upload-artifact). Review dependencies' licenses, notices and distribution obligations as part of the release; the project's MIT license does not change third-party licenses (including Qt/PySide).

## Verify before publishing

Run the [manual Windows/account checks](manual-verification.md) on an independent Windows profile or clean machine without Python. Cover onboarding, local-only tasks, a real Google consent/loopback callback, two accounts, token refresh/revocation/reconnection, offline cache, Moodle feeds, tray reminders and restart. Check the site/policies describe the actual artifact. The automated content check detects common private/development filenames and malformed OAuth resources; it is not a proof that arbitrary files contain no private data.

After Google Cloud changes, authorize a **new account that is not a tester**, using the exact Desktop client in the candidate. Confirm normal access, requested scopes, no unverified warning after approval, and independence of a second account. Also retest an older account after explicit reauthorization; publishing does not automatically convert an old Testing token into an unlimited token. Do not claim permanent sign-in or Google approval based on a mocked test.

The website links to the repository's Releases page without inventing an available version. When ready, the owner manually chooses a tag/version and uses **Releases → Draft a new release**. Attach the candidate ZIP/checksum and describe tested Windows versions, unsigned portable-folder status, Google availability and any limits. Review the release before clicking **Publish release**. No release is automatically created by these scripts.

## Exact owner sequence

The initial source commit/push, publisher/contact and policy finalization, and GitHub Pages deployment were completed on October 31, 2026. The [website guide](PUBLIC_SITE.md#published-website) records the live URLs. The sequence below remains a reference for release preparation and future updates.

1. Review the [audit](RELEASE_AUDIT.md), [security review](SECURITY_REVIEW.md), code, workflows and this candidate. Commit/push only reviewed source and public site assets; leave private configuration ignored.
2. Review privacy/terms text and confirm **Unified Scheduler** and **cuizon.morell@gmail.com** as public publisher/contact details. Choose a developer-owned domain and configure its DNS/ownership verification.
3. Configure GitHub Pages and run its manual workflow following [PUBLIC_SITE.md](PUBLIC_SITE.md). Open the deployed homepage, privacy and terms pages without signing in, on desktop and mobile. Configure HTTPS and the custom domain; record the actual final URLs.
4. Confirm the correct Google Cloud project and Desktop client, enable Calendar API, set External audience, and supply the same app name, support email, homepage/privacy/terms URLs and verified authorized domain.
5. Declare the exact four current scopes and their justifications. Prepare the demonstration video and complete the brand/data-access review and Production steps described in [GOOGLE_OAUTH_PUBLICATION.md](GOOGLE_OAUTH_PUBLICATION.md). Only Google can approve verification; Production alone may still show warnings/user caps.
6. Supply the correct Desktop JSON locally or in the protected `release-build` environment secret. Build a candidate with Google enabled. Neither GitHub Pages nor GitHub Releases configures the Cloud project automatically.
7. Complete the real-account and Windows checks above, including a user outside the tester list and fresh consent after the transition. Record any Google-imposed restrictions truthfully.
8. Review the exact ZIP, checksum, license notices and release notes; sign/package further if desired. Manually draft and publish the GitHub Release only when satisfied. Keep the source, published policies, released artifact and Console declarations consistent.

## Completion boundaries

| State | What it means |
| --- | --- |
| Implemented and tested | Local code and checks recorded in [verification.md](verification.md); owner-supplied Desktop config, read-only OAuth, isolated credentials, packaging and source website files |
| Website published | GitHub Pages deployment succeeded October 31, 2026; homepage, privacy, terms and assets are public over HTTPS. See [PUBLIC_SITE.md](PUBLIC_SITE.md#published-website). |
| Implemented but requires manual testing | Checks outside the agent's completed verification include real Google consent and refresh, no-tester/new-user Production acceptance, clean Windows install/extraction and phone rendering. The developer confirmed the API works and testing is complete on October 31. |
| Requires developer configuration as applicable | Real Desktop client for release builds, owned domain/DNS, GitHub release-build environment/secret, Cloud settings and manual release publication |
| Requires Google approval | Brand and applicable sensitive-scope verification; no such approval has been observed or claimed |
