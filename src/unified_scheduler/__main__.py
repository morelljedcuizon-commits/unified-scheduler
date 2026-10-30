"""Run with ``python -m unified_scheduler``; credentials are entirely optional."""
import argparse
from pathlib import Path
import sys
import tempfile


def main(argv=None):
    parser = argparse.ArgumentParser(description="Unified Scheduler native desktop application")
    parser.add_argument("--demo", action="store_true", help="Use a separate temporary sample workspace; never connect online")
    parser.add_argument("--data-dir", type=Path, help="Override the per-user data directory")
    parser.add_argument("--smoke-test", action="store_true", help="Exercise GUI startup and exit automatically")
    parser.add_argument("--minimized", action="store_true", help="Start in the system tray when available")
    args = parser.parse_args(argv)

    from PySide6.QtCore import QLockFile, QStandardPaths, QTimer
    from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon
    from unified_scheduler.credentials import CredentialStore
    from unified_scheduler.database import Repository
    from unified_scheduler.timeutils import default_timezone
    from unified_scheduler.ui.main_window import MainWindow

    app = QApplication(sys.argv[:1])
    app.setOrganizationName("UnifiedScheduler")
    app.setApplicationName("Unified Scheduler")
    app.setApplicationVersion("1.0.0")
    app.setStyle("Fusion")
    app.setQuitOnLastWindowClosed(False)
    temporary = tempfile.TemporaryDirectory(prefix="UnifiedScheduler-demo-") if args.demo else None
    directory = Path(temporary.name) if temporary else args.data_dir or Path(QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation))
    directory.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(directory / "scheduler.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        QMessageBox.information(None, "Unified Scheduler is already running", "This workspace is already open. Look for Unified Scheduler in the system tray.")
        return 1
    repo = None
    previous_hook = sys.excepthook
    failures = []
    try:
        repo = Repository(directory / "scheduler.sqlite3")
        if repo.get_setting("timezone") is None:
            repo.set_setting("timezone", default_timezone())
        if args.demo:
            from unified_scheduler.demo import seed_demo
            seed_demo(repo, repo.get_setting("timezone"))
        # Workspace-specific vault namespaces also isolate explicit --data-dir profiles.
        from hashlib import sha256
        namespace = sha256(str(directory.resolve()).casefold().encode()).hexdigest()[:20]
        credentials = CredentialStore("UnifiedScheduler:" + namespace)
        window = MainWindow(repo, credentials, demo=args.demo, smoke_test=args.smoke_test)

        def gui_error(error_type, error, traceback):
            # Never log exception bodies: third-party errors may include secrets.
            failures.append(error_type.__name__)
            if args.smoke_test:
                app.exit(1)
            else:
                QMessageBox.warning(window, "The action could not finish", "Please retry the action. If it keeps failing, restart Unified Scheduler. No calendar credentials were written to a log.")
        sys.excepthook = gui_error
        if not args.minimized or not QSystemTrayIcon.isSystemTrayAvailable() or args.smoke_test:
            window.show()
        if args.smoke_test:
            def finish_smoke():
                # Verify frozen provider dependencies and packaged discovery/timezone
                # data without making a network request or touching stored secrets.
                from datetime import date
                import httplib2
                from googleapiclient.discovery import build
                from unified_scheduler.providers.moodle import parse_ics
                from unified_scheduler.providers.google import GoogleProvider
                service = build("calendar", "v3", http=httplib2.Http(),
                                cache_discovery=False, static_discovery=True)
                service.close()
                GoogleProvider(repo, credentials)
                sample = b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:smoke\r\nDTSTART;VALUE=DATE:20261030\r\nDTEND;VALUE=DATE:20261031\r\nSUMMARY:Smoke test\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
                assert len(parse_ics(sample, "smoke", "smoke", date(2026, 10, 29), date(2026, 11, 1), "Asia/Manila")) == 1
                if sys.platform == "win32":
                    from keyring.backends.Windows import WinVaultKeyring
                    assert WinVaultKeyring().priority > 0
                # Exercise navigation and all calendar renderers in the frozen app too.
                for page in ("Today", "Calendar", "Upcoming", "Tasks", "Accounts", "Settings"):
                    window.navigate(page)
                    app.processEvents()
                window.navigate("Calendar")
                for mode in ("Day", "Week", "Month", "Agenda"):
                    window.calendar_view.mode_box.setCurrentText(mode)
                    app.processEvents()
                window.navigate("Today")
                window.quitting = True
                window.close()
            QTimer.singleShot(1200, finish_smoke)
        result = app.exec()
    finally:
        sys.excepthook = previous_hook
        if repo:
            repo.close()
        lock.unlock()
        if temporary:
            temporary.cleanup()
    return 1 if failures else result


if __name__ == "__main__":
    raise SystemExit(main())
