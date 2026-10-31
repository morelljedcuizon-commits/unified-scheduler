Unified Scheduler - Windows desktop application

Extract the entire ZIP before opening UnifiedScheduler.exe. Keep the _internal
folder beside the executable. Python and development tools are not needed.
This is a portable folder build, not an installer. It is not code-signed.

Start with local tasks, or choose Connect Google account. Google sign-in opens
your default browser; return to the app after consent. A Google-enabled build
already contains the application's Desktop OAuth configuration. You never need
your own Google Cloud project or a JSON file. If this build has no Google client,
local tasks and Moodle calendars remain available. Check build-info.json and
the release notes for what this package includes. A bundled client alone does
not mean Google has approved the application's Production/verification status.

Google Calendar and Moodle calendars are read-only. Local completion does not
change Google's events or submit coursework. Use Accounts to connect additional
Google accounts or add your private Moodle HTTPS calendar export URL.

Account tokens and Moodle URLs use Windows Credential Manager. Calendar content
and tasks use a local SQLite database, normally at:
%LOCALAPPDATA%\UnifiedScheduler\Unified Scheduler\scheduler.sqlite3
This database contains personal content and is not encrypted by the app.
Settings shows the actual data location. Do not share it publicly.

Disconnect/Remove an account in Accounts to remove its local credentials and
cached events. Disconnect does not revoke Google's remote consent; manage that
at https://myaccount.google.com/connections . Delete local tasks in the app.
For full removal, disconnect all sources first, disable Start with Windows,
Quit through the tray, then remove the data directory and any backups you own.
Deleting the application folder alone does not delete per-user data or vault
credentials. Closing the window may keep the app running in the tray.

Reminders and automatic synchronization require the app to keep running.
Windows notifications, internet access and provider permissions affect behavior.
Cached events remain available offline but may be stale or outside a feed's
export window. Verify important deadlines with the original calendar provider.

Support/privacy contact: cuizon.morell@gmail.com
Source and release notes:
https://github.com/morelljedcuizon-commits/unified-scheduler
Privacy and terms source (the release page should also link the published site):
https://github.com/morelljedcuizon-commits/unified-scheduler/tree/main/docs/public-site
Do not include tokens, private Moodle URLs or personal calendars in public issues.

The application's MIT license is included as LICENSE. Dependencies have their
own licenses. Review the license files in _internal and the release documentation.
