"""The native application shell, dashboard, accounts and settings."""
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path
import sys
from zoneinfo import ZoneInfo, available_timezones

from PySide6.QtCore import QDate, QThreadPool, QTimer, Qt, QUrl, Slot
from PySide6.QtGui import QAction, QColor, QDesktopServices, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QCalendarWidget, QCheckBox, QColorDialog, QComboBox, QDateEdit,
    QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMenu, QMessageBox, QPushButton, QScrollArea, QSpinBox, QSplitter,
    QSizePolicy, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget,
)
from unified_scheduler.aggregation import Aggregator
from unified_scheduler.reminders import ReminderService
from unified_scheduler.timeutils import default_timezone, event_start, event_end
from unified_scheduler.ui.dialogs import MoodleDialog, TaskDialog, WelcomeDialog, reminder_combo, text_label
from unified_scheduler.ui.theme import apply_theme
from unified_scheduler.ui.widgets import CalendarView, EventRow, SOURCE_COLORS, SOURCE_NAMES, time_caption
from unified_scheduler.ui.workers import Worker


def application_icon():
    if getattr(sys, "frozen", False):
        icon_path = Path(sys._MEIPASS) / "assets" / "unified_scheduler_simple.ico"
    else:
        icon_path = Path(__file__).resolve().parents[3] / "assets" / "unified_scheduler_simple.ico"
    icon = QIcon(str(icon_path))
    if icon.isNull():
        raise FileNotFoundError(f"Unified Scheduler icon was not found: {icon_path}")
    return icon


def clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().hide()
            item.widget().deleteLater()
        elif item.layout():
            clear_layout(item.layout())
            item.layout().deleteLater()


def scroll_page():
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    content = QWidget()
    content.setObjectName("page")
    layout = QVBoxLayout(content)
    layout.setContentsMargins(0, 0, 10, 12)
    layout.setSpacing(12)
    scroll.setWidget(content)
    return scroll, layout


class MainWindow(QMainWindow):
    def __init__(self, repository, credentials, demo=False, smoke_test=False):
        super().__init__()
        self.repo, self.credentials, self.demo = repository, credentials, demo
        self.aggregator = Aggregator(repository)
        self.reminders = ReminderService(repository, self.aggregator)
        self.timezone = self.repo.get_setting("timezone", default_timezone())
        self.current_page = "Today"
        self.selected_event = None
        self.workers = set()
        self.worker_callbacks = {}
        self.busy = False
        self.quitting = False
        self.smoke_test = smoke_test
        self.last_notification = None
        self.setWindowTitle("Unified Scheduler" + (" · DEMO" if demo else ""))
        self.setWindowIcon(application_icon())
        self.resize(1400, 860)
        self.setMinimumSize(1000, 650)
        self.palette_colors = apply_theme(QApplication.instance(), self.repo.get_setting("theme", "light"))
        self.build_shell()
        self.build_tray()
        self.sync_timer = QTimer(self)
        self.sync_timer.timeout.connect(self.sync)
        self.reset_sync_timer()
        self.reminder_timer = QTimer(self)
        self.reminder_timer.timeout.connect(self.check_reminders)
        if not smoke_test:
            self.reminder_timer.start(30000)
        self.date_timer = QTimer(self)
        self.date_timer.timeout.connect(self.refresh_at_midnight)
        self.date_timer.start(60000)
        self.last_day = self.today()
        self.refresh()
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self.add_task)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self.search.setFocus)
        QShortcut(QKeySequence("F5"), self, activated=self.sync)
        if not smoke_test:
            QTimer.singleShot(500, self.first_launch)

    def today(self):
        return datetime.now(ZoneInfo(self.timezone)).date()

    def build_shell(self):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(226)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(16, 24, 16, 18)
        side.setSpacing(6)
        brand = QHBoxLayout()
        logo = text_label("", "logo")
        logo.setPixmap(application_icon().pixmap(42, 42))
        logo.setAlignment(Qt.AlignCenter)
        logo.setFixedSize(42, 42)
        brand.addWidget(logo)
        brand.addWidget(text_label("Unified\nScheduler", "section"), 1)
        side.addLayout(brand)
        side.addSpacing(27)
        side.addWidget(text_label("YOUR WORKSPACE", "eyebrow"))
        side.addSpacing(5)
        self.nav = {}
        for name, symbol in (("Today", "◉"), ("Calendar", "▦"), ("Upcoming", "↗"), ("Tasks", "✓"), ("Accounts", "◎"), ("Settings", "⚙")):
            button = QPushButton(f"{symbol}    {name}")
            button.setObjectName("nav")
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, page=name: self.navigate(page))
            self.nav[name] = button
            side.addWidget(button)
        side.addSpacing(25)
        self.mini_calendar = QCalendarWidget()
        self.mini_calendar.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self.mini_calendar.setHorizontalHeaderFormat(QCalendarWidget.SingleLetterDayNames)
        self.mini_calendar.setFirstDayOfWeek(Qt.Monday)
        self.mini_calendar.setGridVisible(False)
        self.mini_calendar.setFixedHeight(205)
        self.mini_calendar.setMinimumWidth(0)
        self.mini_calendar.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.mini_calendar.clicked.connect(self.select_date)
        side.addWidget(self.mini_calendar)
        side.addStretch()
        side.addWidget(text_label("ONE DAY AT A TIME", "eyebrow"))
        side.addWidget(text_label("Local first. Yours to organize.", "muted"))
        outer.addWidget(self.sidebar)
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        outer.addWidget(self.splitter, 1)
        main = QWidget()
        main.setObjectName("page")
        body = QVBoxLayout(main)
        body.setContentsMargins(28, 23, 24, 12)
        body.setSpacing(16)
        if self.demo:
            body.addWidget(text_label("DEMO · Sample workspace · Changes are temporary · Connections are disabled", "banner"))
        top = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(5)
        self.heading = text_label("Today", "title")
        self.subtitle = text_label("", "muted")
        titles.addWidget(self.heading)
        titles.addWidget(self.subtitle)
        top.addLayout(titles, 1)
        self.sync_button = QPushButton("↻  Sync")
        self.sync_button.clicked.connect(self.sync)
        self.sync_button.setToolTip("Refresh connected calendars (F5)")
        top.addWidget(self.sync_button)
        add = QPushButton("＋  Add task")
        add.setObjectName("primary")
        add.clicked.connect(self.add_task)
        top.addWidget(add)
        body.addLayout(top)
        self.filter_bar = QWidget()
        filters = QHBoxLayout(self.filter_bar)
        filters.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search title or description…   Ctrl+F")
        self.search.setClearButtonEnabled(True)
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(180)
        self.search_timer.timeout.connect(self.refresh_content)
        self.search.textChanged.connect(lambda _: self.search_timer.start())
        filters.addWidget(self.search, 1)
        self.source_filter = QComboBox()
        self.source_filter.setMinimumWidth(140)
        self.source_filter.currentIndexChanged.connect(self.refresh_content)
        filters.addWidget(self.source_filter)
        self.show_completed = QCheckBox("Completed")
        self.show_completed.setChecked(True)
        self.show_completed.toggled.connect(self.refresh_content)
        filters.addWidget(self.show_completed)
        body.addWidget(self.filter_bar)
        self.date_filters = QWidget()
        dates = QHBoxLayout(self.date_filters)
        dates.setContentsMargins(0, 0, 0, 0)
        self.use_dates = QCheckBox("Date range")
        self.date_from = QDateEdit(QDate.currentDate().addDays(-7))
        self.date_to = QDateEdit(QDate.currentDate().addDays(30))
        for field in (self.date_from, self.date_to):
            field.setCalendarPopup(True)
            field.setDisplayFormat("dd MMM yyyy")
            field.dateChanged.connect(self.refresh_content)
            field.setEnabled(False)
        self.use_dates.toggled.connect(self.toggle_dates)
        dates.addWidget(self.use_dates)
        dates.addWidget(self.date_from)
        dates.addWidget(text_label("to", "muted"))
        dates.addWidget(self.date_to)
        dates.addStretch()
        body.addWidget(self.date_filters)
        self.stack = QStackedWidget()
        self.pages = {}
        self.layouts = {}
        for name in ("Today", "Calendar", "Upcoming", "Tasks", "Accounts", "Settings"):
            if name == "Calendar":
                self.calendar_view = CalendarView()
                self.calendar_view.anchor = self.today()
                self.calendar_view.eventSelected.connect(self.show_detail)
                self.calendar_view.rangeChanged.connect(self.refresh_content)
                self.calendar_view.dateSelected.connect(lambda day: self.add_task(selected_date=day))
                widget = self.calendar_view
            else:
                widget, self.layouts[name] = scroll_page()
            self.pages[name] = widget
            self.stack.addWidget(widget)
        body.addWidget(self.stack, 1)
        self.splitter.addWidget(main)
        self.detail_scroll = QScrollArea()
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setMinimumWidth(240)
        self.detail_scroll.setMaximumWidth(360)
        detail = QFrame()
        detail.setObjectName("detail")
        self.details = QVBoxLayout(detail)
        self.details.setContentsMargins(22, 26, 22, 22)
        self.details.setSpacing(13)
        self.detail_scroll.setWidget(detail)
        self.splitter.addWidget(self.detail_scroll)
        self.splitter.setSizes([850, 280])
        self.statusBar().showMessage("Your local calendar is ready.")

    def build_tray(self):
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip("Unified Scheduler")
        menu = QMenu(self)
        menu.addAction("Open Unified Scheduler", self.restore)
        menu.addAction("Add task", self.add_from_tray)
        menu.addAction("Sync calendars", self.sync)
        menu.addSeparator()
        menu.addAction("Quit", self.quit_app)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.restore() if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick) else None)
        self.tray.messageClicked.connect(self.open_notification)
        if QSystemTrayIcon.isSystemTrayAvailable() and not self.smoke_test:
            self.tray.show()

    def restore(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def add_from_tray(self):
        self.restore()
        self.add_task()

    def first_launch(self):
        if not self.demo and not self.repo.get_setting("onboarded", False):
            dialog = WelcomeDialog(self)
            dialog.exec()
            self.repo.set_setting("onboarded", True)
            if dialog.choice == "google":
                self.connect_google()
            elif dialog.choice == "moodle":
                self.add_moodle()
        if not self.busy and self.has_sync_sources():
            self.sync()

    def has_sync_sources(self):
        return any(account.kind in ("google", "moodle") for account in self.repo.list_accounts())

    def navigate(self, page):
        self.current_page = page
        self.stack.setCurrentWidget(self.pages[page])
        self.refresh_content()

    def select_date(self, value):
        self.calendar_view.anchor = value.toPython()
        self.navigate("Calendar")

    def toggle_dates(self, checked):
        self.date_from.setEnabled(checked)
        self.date_to.setEnabled(checked)
        self.refresh_content()

    def refresh(self):
        selected_filter = self.source_filter.currentData()
        self.source_filter.blockSignals(True)
        self.source_filter.clear()
        self.source_filter.addItem("All sources", None)
        for source in ("local", "google", "moodle"):
            self.source_filter.addItem(SOURCE_NAMES[source], "source:" + source)
        for calendar in self.repo.list_calendars():
            if calendar.id != "local":
                self.source_filter.addItem(calendar.name, "calendar:" + calendar.id)
        index = self.source_filter.findData(selected_filter)
        self.source_filter.setCurrentIndex(max(0, index))
        self.source_filter.blockSignals(False)
        self.refresh_content()

    def filtered_events(self, start, end):
        if self.use_dates.isChecked() and self.current_page in ("Upcoming", "Tasks"):
            start = self.date_from.date().toPython()
            end = self.date_to.date().toPython() + timedelta(days=1)
        if end <= start:
            return []
        value = self.source_filter.currentData()
        calendars = None
        if value and value.startswith("calendar:"):
            calendars = [value[9:]]
        events = self.aggregator.events(start, end, self.timezone, calendar_ids=calendars,
                                      search=self.search.text(), include_completed=self.show_completed.isChecked(),
                                      deduplicate=self.repo.get_setting("visual_dedup", False))
        if value and value.startswith("source:"):
            events = [event for event in events if event.source == value[7:]]
        return events

    def refresh_content(self, *_):
        if not hasattr(self, "stack"):
            return
        page = self.current_page
        self.heading.setText(page)
        self.subtitle.setText({
            "Today": self.today().strftime("%A, %B %d, %Y") + "  ·  " + self.timezone,
            "Calendar": "Find a little space in your schedule.",
            "Upcoming": "A clear view of what's next.",
            "Tasks": "Small steps. Steady progress.",
            "Accounts": "Your calendars, connected securely.",
            "Settings": "Make this workspace yours.",
        }[page])
        for name, button in self.nav.items():
            button.setChecked(name == page)
        self.filter_bar.setVisible(page not in ("Accounts", "Settings"))
        self.date_filters.setVisible(page in ("Upcoming", "Tasks"))
        self.detail_scroll.setVisible(page not in ("Accounts", "Settings") and self.width() >= 1160)
        self.calendars = {calendar.id: calendar for calendar in self.repo.list_calendars()}
        self.accounts = {account.id: account for account in self.repo.list_accounts()}
        if page == "Calendar":
            start, end = self.calendar_view.range()
            self.calendar_view.render(self.filtered_events(start, end), self.timezone,
                                      {key: value.color for key, value in self.calendars.items()})
        else:
            layout = self.layouts[page]
            clear_layout(layout)
            if page == "Today":
                self.render_today(layout)
            elif page in ("Upcoming", "Tasks"):
                self.render_list(layout, page)
            elif page == "Accounts":
                self.render_accounts(layout)
            else:
                self.render_settings(layout)
        if self.selected_event:
            self.render_detail(self.selected_event)
        else:
            self.render_sidebar_summary()

    def card(self):
        frame = QFrame()
        frame.setObjectName("card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(19, 17, 19, 17)
        layout.setSpacing(12)
        return frame, layout

    def add_section(self, layout, title, events, show_date=False, empty=None):
        header = QHBoxLayout()
        header.addWidget(text_label(title, "section"))
        header.addStretch()
        header.addWidget(text_label(str(len(events)), "muted"))
        layout.addLayout(header)
        if not events and empty:
            frame, box = self.card()
            box.addWidget(text_label(empty, "muted"))
            layout.addWidget(frame)
        for event in events:
            calendar = self.calendars.get(event.calendar_id)
            row = EventRow(event, self.timezone, calendar.name if calendar else "",
                           event.color or (calendar.color if calendar else ""), show_date)
            row.selected.connect(self.show_detail)
            row.completionChanged.connect(self.complete_event)
            layout.addWidget(row)

    def is_overdue(self, event):
        if event.status == "Completed" or not (event.kind == "task" or event.source == "moodle"):
            return False
        boundary = event_end(event, self.timezone) if event.all_day else event_start(event, self.timezone)
        return boundary < datetime.now(ZoneInfo(self.timezone))

    def render_today(self, layout):
        today = self.today()
        events = self.filtered_events(self.history_start(), today + timedelta(days=31))
        todays = [event for event in events if event_start(event, self.timezone).date() <= today and
                  (event_end(event, self.timezone).date() > today or event_start(event, self.timezone).date() == today or
                   not event.all_day and event_end(event, self.timezone).date() == today and event_end(event, self.timezone).hour > 0)]
        tasks = [e for e in todays if e.kind == "task" or e.source == "moodle"]
        overdue = [e for e in events if self.is_overdue(e)]
        overdue_ids = {e.id for e in overdue}
        statistics = QHBoxLayout()
        for title, value, subtitle in (("TODAY'S TASKS", str(len(tasks)), "A manageable day ahead"),
                                       ("COMPLETED", str(sum(e.status == "Completed" for e in tasks)), "Every step counts"),
                                       ("OVERDUE", str(len(overdue)), "Ready when you are")):
            frame, box = self.card()
            box.addWidget(text_label(title, "eyebrow"))
            box.addWidget(text_label(value, "stat"))
            box.addWidget(text_label(subtitle, "muted"))
            statistics.addWidget(frame, 1)
        layout.addLayout(statistics)
        layout.addSpacing(9)
        if overdue:
            self.add_section(layout, "Needs your attention", overdue, True)
        all_day = [e for e in todays if e.all_day and e.id not in overdue_ids]
        if all_day:
            self.add_section(layout, "All day & deadlines", all_day)
        self.add_section(layout, "Your day, in order", [e for e in todays if not e.all_day and e.id not in overdue_ids],
                         empty="Your day has room to breathe. Add a task, or connect Google and Moodle calendars.")
        coming = [e for e in events if event_start(e, self.timezone).date() > today and e.status != "Completed"][:6]
        if coming:
            self.add_section(layout, "On the horizon", coming, True)
        layout.addStretch()

    def history_start(self):
        start = self.today() - timedelta(days=365)
        for event in self.repo.list_local_events() + self.repo.list_cached_events():
            if not event.recurrence:
                start = min(start, event_start(event, self.timezone).date())
        return start

    def render_list(self, layout, page):
        today = self.today()
        start = today if page == "Upcoming" else self.history_start()
        end = today + timedelta(days=180)
        events = self.filtered_events(start, end)
        if page == "Tasks":
            events = [e for e in events if e.kind == "task" or e.source == "moodle"]
        if not events:
            self.add_section(layout, "All clear", [], empty="No entries match this view. Try another filter, add a task, or connect a calendar.")
        previous_date = None
        for event in events:
            day = event_start(event, self.timezone).date()
            if day != previous_date:
                layout.addSpacing(6)
                layout.addWidget(text_label(day.strftime("%A, %d %B %Y"), "section"))
                previous_date = day
            calendar = self.calendars.get(event.calendar_id)
            row = EventRow(event, self.timezone, calendar.name if calendar else "", event.color or (calendar.color if calendar else ""))
            row.selected.connect(self.show_detail)
            row.completionChanged.connect(self.complete_event)
            layout.addWidget(row)
        layout.addStretch()

    def render_sidebar_summary(self):
        clear_layout(self.details)
        self.details.addWidget(text_label("AT A GLANCE", "eyebrow"))
        self.details.addWidget(text_label("Everything in its place", "section"))
        self.details.addWidget(text_label("Select an entry to see its details, track completion or set a reminder.", "muted"))
        self.details.addSpacing(14)
        self.details.addWidget(text_label("Calendar sources", "section"))
        self.details.addWidget(text_label("●  Local calendar\nSaved on this device", "muted"))
        for account in self.accounts.values():
            if account.kind == "local":
                continue
            label = text_label(account.label)
            self.details.addWidget(label)
            message = account.status.title()
            if account.last_sync:
                try:
                    synced = datetime.fromisoformat(account.last_sync).astimezone(ZoneInfo(self.timezone))
                    message += f" · {synced:%d %b, %H:%M}"
                except ValueError:
                    pass
            self.details.addWidget(text_label(message, "muted"))
            if account.error:
                self.details.addWidget(text_label("Cached events retained. " + account.error, "muted"))
        self.details.addStretch()
        self.details.addWidget(text_label("A moment of focus", "eyebrow"))
        self.details.addWidget(text_label("Choose one small thing to move forward today.", "muted"))

    def show_detail(self, event):
        self.selected_event = event
        self.render_detail(event)
        if self.width() < 1160:
            # The resizable splitter provides details on demand on smaller displays.
            self.detail_scroll.show()
            self.splitter.setSizes([max(350, self.width() - 510), 260])

    def render_detail(self, event):
        clear_layout(self.details)
        top = QHBoxLayout()
        top.addWidget(text_label("ENTRY DETAILS", "eyebrow"), 1)
        close = QPushButton("×")
        close.setFixedWidth(32)
        close.setAccessibleName("Close entry details")
        close.clicked.connect(self.clear_detail)
        top.addWidget(close)
        self.details.addLayout(top)
        self.details.addWidget(text_label(event.title, "section"))
        self.details.addWidget(text_label(time_caption(event, self.timezone, True)))
        calendar = self.calendars.get(event.calendar_id)
        account = self.accounts.get(event.account_id)
        source = SOURCE_NAMES.get(event.source, event.source)
        if account:
            source += " · " + account.label
        if calendar and calendar.name != "Local":
            source += "\n" + calendar.name
        self.details.addWidget(text_label(source, "muted"))
        if event.source != "local":
            self.details.addWidget(text_label("Read-only source · Completion is tracked on this device. It does not submit work or change the original event.", "muted"))
        if event.description:
            self.details.addWidget(text_label(event.description))
        if event.location:
            self.details.addWidget(text_label("Location\n" + event.location, "muted"))
        if event.category:
            self.details.addWidget(text_label("Category · " + event.category, "muted"))
        self.details.addWidget(text_label(f"{event.priority} priority · {event.status}", "muted"))
        if event.recurrence:
            self.details.addWidget(text_label("Repeats " + event.recurrence + ". Editing changes the series.", "muted"))
        completion = QCheckBox("Completed locally")
        completion.setChecked(event.status == "Completed")
        completion.toggled.connect(lambda checked: self.complete_event(event, checked))
        self.details.addWidget(completion)
        self.details.addWidget(text_label("Reminder", "section"))
        # Persisted per-occurrence configuration is independent of provider refreshes.
        state = self.repo.reminder_states().get(event.id, {})
        value = state.get("reminder_minutes") if state.get("configured") else event.reminder_minutes
        reminder = reminder_combo(value if value is not None else -1)
        reminder.currentIndexChanged.connect(lambda: self.configure_reminder(event, reminder.currentData()))
        self.details.addWidget(reminder)
        row = QHBoxLayout()
        snooze, dismiss = QPushButton("Snooze 10m"), QPushButton("Dismiss")
        snooze.clicked.connect(lambda: self.snooze(event))
        dismiss.clicked.connect(lambda: self.dismiss(event))
        row.addWidget(snooze)
        row.addWidget(dismiss)
        self.details.addLayout(row)
        if event.url and QUrl(event.url).scheme() in ("https", "http"):
            original = QPushButton("Open original event ↗")
            original.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(event.url)))
            self.details.addWidget(original)
        if event.source == "local":
            edit = QPushButton("Edit series" if event.recurrence else "Edit entry")
            edit.clicked.connect(lambda: self.edit_task(event))
            self.details.addWidget(edit)
            delete = QPushButton("Delete series" if event.recurrence else "Delete entry")
            delete.setObjectName("danger")
            delete.clicked.connect(lambda: self.delete_task(event))
            self.details.addWidget(delete)
        self.details.addStretch()

    def clear_detail(self):
        self.selected_event = None
        self.render_sidebar_summary()
        if self.width() < 1160:
            self.detail_scroll.hide()

    def complete_event(self, event, checked):
        self.repo.set_completion(event.id, checked)
        event.status = "Completed" if checked else "Pending"
        if self.selected_event and self.selected_event.id == event.id:
            self.selected_event = event
        self.refresh_content()

    def configure_reminder(self, event, minutes):
        self.reminders.configure(event.id, None if minutes < 0 else minutes)
        self.statusBar().showMessage("Reminder updated for this occurrence.", 4000)

    def snooze(self, event):
        self.reminders.snooze(event.id, 10)
        self.statusBar().showMessage("Reminder snoozed for 10 minutes.", 4000)

    def dismiss(self, event):
        self.reminders.dismiss(event.id)
        self.statusBar().showMessage("Reminder dismissed for this occurrence.", 4000)

    def add_task(self, checked=False, selected_date=None):
        dialog = TaskDialog(self, self.timezone, selected_date=selected_date or self.today(),
                            default_reminder=self.repo.get_setting("default_reminder", 30))
        if dialog.exec():
            self.repo.save_local_event(dialog.result_event)
            self.refresh()

    def edit_task(self, event):
        original = self.repo.get_local_event(event.task_id or event.id)
        if not original:
            return
        dialog = TaskDialog(self, self.timezone, event=original)
        if dialog.exec():
            self.repo.save_local_event(dialog.result_event)
            self.selected_event = None
            self.refresh()

    def delete_task(self, event):
        answer = QMessageBox.question(self, "Delete local entry", "Delete this entry" + (" and every occurrence in its series?" if event.recurrence else "?"),
                                      QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer == QMessageBox.Yes:
            self.repo.delete_local_event(event.task_id or event.id)
            self.selected_event = None
            self.refresh()

    def render_accounts(self, layout):
        actions = QHBoxLayout()
        google = QPushButton("＋  Connect Google account")
        moodle = QPushButton("＋  Add Moodle calendar")
        google.setObjectName("primary")
        google.clicked.connect(self.connect_google)
        moodle.clicked.connect(self.add_moodle)
        for button in (google, moodle):
            button.setEnabled(not self.demo and not self.busy)
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)
        layout.addWidget(text_label("Google and Moodle are read-only. Local completion never changes the original event. Each account and feed has its own cache and secure credentials.", "muted"))
        frame, local_box = self.card()
        local_box.addWidget(text_label("Local calendar", "section"))
        local_box.addWidget(text_label("Your tasks and events stay on this Windows profile, ready offline.", "muted"))
        local = self.calendars.get("local")
        if local:
            self.calendar_controls(local_box, local)
        layout.addWidget(frame)
        for account in self.accounts.values():
            if account.kind == "local":
                continue
            card, box = self.card()
            heading = QHBoxLayout()
            heading.addWidget(text_label(account.label, "section"), 1)
            heading.addWidget(text_label(SOURCE_NAMES.get(account.kind, account.kind).upper(), "eyebrow"))
            box.addLayout(heading)
            if account.kind == "google":
                box.addWidget(text_label("Verified Google account · Read-only access", "muted"))
            last = "Never synced"
            if account.last_sync:
                try:
                    last = datetime.fromisoformat(account.last_sync).astimezone(ZoneInfo(self.timezone)).strftime("%d %b %Y at %H:%M")
                except ValueError:
                    last = "Available"
            status = "Reconnect required" if account.status == "reauthenticate" else account.status.title()
            box.addWidget(text_label(f"{status} · Last successful sync: {last}", "muted"))
            if account.error:
                box.addWidget(text_label(account.error + " Cached events remain available.", "muted"))
            for calendar in self.repo.list_calendars(account.id):
                self.calendar_controls(box, calendar)
            controls = QHBoxLayout()
            refresh = QPushButton("Refresh now")
            refresh.clicked.connect(self.sync)
            controls.addWidget(refresh)
            if account.kind == "moodle":
                edit = QPushButton("Edit calendar")
                edit.clicked.connect(lambda checked=False, a=account: self.add_moodle(account=a))
            else:
                edit = QPushButton("Reconnect Google account")
                edit.clicked.connect(lambda checked=False, a=account: self.connect_google(account=a))
            controls.addWidget(edit)
            remove = QPushButton("Remove" if account.kind == "moodle" else "Disconnect")
            remove.setObjectName("danger")
            remove.clicked.connect(lambda checked=False, a=account: self.remove_account(a))
            controls.addWidget(remove)
            controls.addStretch()
            for button in (refresh, edit, remove):
                button.setEnabled(not self.demo and not self.busy)
            box.addLayout(controls)
            layout.addWidget(card)
        if not [a for a in self.accounts.values() if a.kind != "local"]:
            frame, box = self.card()
            box.addWidget(text_label("Bring your day together", "section"))
            box.addWidget(text_label("Connect any number of Google accounts or private Moodle calendar feeds. You can keep using the local calendar on its own.", "muted"))
            layout.addWidget(frame)
        layout.addStretch()

    def calendar_controls(self, layout, calendar):
        row = QHBoxLayout()
        enabled = QCheckBox(calendar.name)
        enabled.setChecked(calendar.enabled)
        enabled.toggled.connect(lambda checked: self.set_calendar_visibility(calendar, checked))
        row.addWidget(enabled, 1)
        color = QPushButton("Color")
        safe_color = QColor(calendar.color).name()
        color.setStyleSheet(f"border-left: 5px solid {safe_color};")
        color.clicked.connect(lambda: self.set_calendar_color(calendar))
        row.addWidget(color)
        layout.addLayout(row)

    def set_calendar_visibility(self, calendar, enabled):
        self.repo.save_calendar(replace(calendar, enabled=enabled))
        self.refresh()

    def set_calendar_color(self, calendar):
        color = QColorDialog.getColor(QColor(calendar.color), self)
        if color.isValid():
            self.repo.save_calendar(replace(calendar, color=color.name()))
            self.refresh()

    def google_provider(self):
        from unified_scheduler.providers.google import GoogleProvider
        return GoogleProvider(self.repo, self.credentials)

    def moodle_provider(self):
        from unified_scheduler.providers.moodle import MoodleProvider
        return MoodleProvider(self.repo, self.credentials)

    def connect_google(self, checked=False, account=None):
        if self.demo or self.busy:
            return
        provider = self.google_provider()
        job = (lambda: provider.reconnect(account.id)) if account else provider.connect
        self.run_job(job, lambda _: self.after_connection(), "Waiting for Google authorization in your browser…")

    def after_connection(self):
        self.statusBar().showMessage("Account connected. Fetching calendars…")
        QTimer.singleShot(50, self.sync)

    def add_moodle(self, checked=False, account=None):
        if self.demo or self.busy:
            return
        color = "#b06a24"
        if account:
            calendars = self.repo.list_calendars(account.id)
            if calendars:
                color = calendars[0].color
        dialog = MoodleDialog(self, self.moodle_provider(), self.timezone, account, color)
        if dialog.exec():
            self.refresh()
            self.sync()

    def remove_account(self, account):
        if self.busy:
            return
        answer = QMessageBox.question(self, "Remove connected source", "Remove this source, its saved credentials and cached events from this device? Local tasks will stay.",
                                      QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer == QMessageBox.Yes:
            function = (lambda: self.google_provider().disconnect(account.id)) if account.kind == "google" else (lambda: self.moodle_provider().remove(account.id))
            self.selected_event = None
            self.run_job(function, lambda _: self.statusBar().showMessage("Source removed."), "Removing source…")

    def render_settings(self, layout):
        card, box = self.card()
        box.addWidget(text_label("Appearance & time", "section"))
        form = QFormLayout()
        form.setSpacing(14)
        theme = QComboBox()
        theme.addItems(["Light", "Dark"])
        theme.setCurrentText(self.repo.get_setting("theme", "light").title())
        zone = QComboBox()
        zone.setEditable(True)
        zone.addItems(sorted(available_timezones()))
        zone.setCurrentText(self.timezone)
        default_reminder = reminder_combo(self.repo.get_setting("default_reminder", 30))
        form.addRow("Theme", theme)
        form.addRow("Display time zone", zone)
        form.addRow("Default reminder", default_reminder)
        box.addLayout(form)
        layout.addWidget(card)
        card, box = self.card()
        box.addWidget(text_label("Sync & behavior", "section"))
        form = QFormLayout()
        form.setSpacing(14)
        interval, past, future = QSpinBox(), QSpinBox(), QSpinBox()
        interval.setRange(5, 1440)
        interval.setSuffix(" minutes")
        interval.setValue(self.repo.get_setting("sync_minutes", 15))
        past.setRange(1, 1825)
        past.setSuffix(" days")
        past.setValue(self.repo.get_setting("sync_past_days", 30))
        future.setRange(1, 730)
        future.setSuffix(" days")
        future.setValue(self.repo.get_setting("sync_future_days", 180))
        form.addRow("Refresh calendars every", interval)
        form.addRow("Cache past events", past)
        form.addRow("Cache upcoming events", future)
        box.addLayout(form)
        tray = QCheckBox("Minimize and close to the system tray")
        tray.setChecked(self.repo.get_setting("minimize_to_tray", True))
        startup = QCheckBox("Start with Windows")
        startup.setChecked(self.repo.get_setting("start_with_windows", False))
        startup.setEnabled(not self.demo)
        dedup = QCheckBox("Visually combine exact Google / Moodle duplicates")
        dedup.setChecked(self.repo.get_setting("visual_dedup", False))
        box.addWidget(tray)
        box.addWidget(startup)
        box.addWidget(dedup)
        box.addWidget(text_label("Notifications work while Unified Scheduler is running, including in the tray. All-day reminders use 9:00 AM. Visual deduplication never deletes source events.", "muted"))
        layout.addWidget(card)
        card, box = self.card()
        box.addWidget(text_label("Google sign-in", "section"))
        box.addWidget(text_label("Choose Connect Google account on the Accounts page. Sign in securely in your browser, then return here. Your connection is remembered on this device; no configuration file is needed from you.", "muted"))
        layout.addWidget(card)
        save = QPushButton("Save settings")
        save.setObjectName("primary")
        def save_settings():
            timezone = zone.currentText().strip()
            try:
                ZoneInfo(timezone)
            except (ValueError, KeyError):
                QMessageBox.warning(self, "Time zone", "Choose a valid IANA time zone, such as Asia/Manila.")
                return
            if not self.demo:
                from unified_scheduler.platform import set_startup
                try:
                    set_startup(startup.isChecked(), str(Path(self.repo.path).parent))
                except (OSError, RuntimeError):
                    QMessageBox.warning(self, "Startup setting", "The Windows startup preference could not be saved.")
                    return
            for key, value in {"theme": theme.currentText().lower(), "timezone": timezone,
                               "default_reminder": None if default_reminder.currentData() < 0 else default_reminder.currentData(), "sync_minutes": interval.value(),
                               "sync_past_days": past.value(), "sync_future_days": future.value(),
                               "minimize_to_tray": tray.isChecked(), "start_with_windows": startup.isChecked(),
                               "visual_dedup": dedup.isChecked()}.items():
                self.repo.set_setting(key, value)
            self.timezone = timezone
            self.palette_colors = apply_theme(QApplication.instance(), theme.currentText().lower())
            self.reset_sync_timer()
            self.statusBar().showMessage("Settings saved.", 5000)
            self.refresh()
        save.clicked.connect(save_settings)
        layout.addWidget(save, 0, Qt.AlignLeft)
        layout.addWidget(text_label("Data location: " + str(self.repo.path), "muted"))
        layout.addStretch()

    def reset_sync_timer(self):
        self.sync_timer.setInterval(max(5, int(self.repo.get_setting("sync_minutes", 15))) * 60000)
        if not self.demo and not self.smoke_test:
            self.sync_timer.start()

    def run_job(self, function, on_success, message):
        if self.busy:
            return
        self.busy = True
        self.sync_button.setEnabled(False)
        self.sync_button.setText("Syncing…")
        self.statusBar().showMessage(message)
        worker = Worker(function)
        self.workers.add(worker)
        self.worker_callbacks[worker] = on_success
        worker.signals.succeeded.connect(self.job_succeeded, Qt.ConnectionType.QueuedConnection)
        worker.signals.failed.connect(self.job_failed, Qt.ConnectionType.QueuedConnection)
        worker.signals.finished.connect(self.job_finished, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker)
        if self.current_page == "Accounts":
            self.refresh_content()

    @Slot(object, object)
    def job_succeeded(self, worker, result):
        callback = self.worker_callbacks.get(worker)
        if callback:
            callback(result)

    @Slot(object, str)
    def job_failed(self, worker, message):
        self.statusBar().showMessage(message)
        QMessageBox.warning(self, "Calendar connection", message)

    @Slot(object)
    def job_finished(self, worker):
        self.workers.discard(worker)
        self.worker_callbacks.pop(worker, None)
        self.busy = False
        self.sync_button.setText("↻  Sync")
        self.sync_button.setEnabled(True)
        self.refresh()

    def sync(self, *_):
        if self.demo:
            self.statusBar().showMessage("Demo workspace uses sample data. Online connections are disabled.", 5000)
            return
        if self.busy:
            return
        if not self.has_sync_sources():
            self.statusBar().showMessage("Local entries are saved. Connect a source in Accounts to sync calendars.", 5000)
            return
        from unified_scheduler.sync import SyncService
        self.run_job(lambda: SyncService(self.repo, self.credentials).sync_all(), self.sync_finished, "Refreshing your calendars…")

    def sync_finished(self, results):
        self.selected_event = None
        failures = [r for r in results if r.status not in ("ok", "success", "synced", "disabled")]
        if failures:
            self.statusBar().showMessage(f"{len(failures)} source(s) need attention. Cached events remain available; see Accounts.")
        else:
            self.statusBar().showMessage("Calendars refreshed · " + datetime.now(ZoneInfo(self.timezone)).strftime("%H:%M"))

    def check_reminders(self):
        if self.demo or not self.tray.isVisible() or not QSystemTrayIcon.supportsMessages():
            return
        events = self.reminders.due(datetime.now(ZoneInfo(self.timezone)), self.timezone)
        if events:
            self.last_notification = events[0]
            title = events[0].title if len(events) == 1 else f"{len(events)} reminders"
            body = time_caption(events[0], self.timezone, True) if len(events) == 1 else "\n".join(e.title for e in events)
            self.tray.showMessage(title, body, QSystemTrayIcon.Information, 10000)

    def open_notification(self):
        self.restore()
        if self.last_notification:
            self.show_detail(self.last_notification)

    def refresh_at_midnight(self):
        if self.today() != self.last_day:
            self.last_day = self.today()
            self.refresh_content()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "detail_scroll"):
            self.detail_scroll.setVisible(self.current_page not in ("Accounts", "Settings") and self.width() >= 1160)

    def changeEvent(self, event):
        from PySide6.QtCore import QEvent
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange and self.isMinimized() and self.repo.get_setting("minimize_to_tray", True) and self.tray.isVisible():
            QTimer.singleShot(0, self.hide)

    def quit_app(self):
        if self.busy:
            self.restore()
            self.statusBar().showMessage("A calendar operation is finishing. Please quit after it completes.")
            return
        self.quitting = True
        self.close()

    def closeEvent(self, event):
        if not self.quitting and not self.smoke_test and self.repo.get_setting("minimize_to_tray", True) and self.tray.isVisible():
            self.hide()
            event.ignore()
            return
        if self.busy:
            self.statusBar().showMessage("A calendar operation is finishing. Please close after it completes.")
            event.ignore()
            return
        self.tray.hide()
        self.sync_timer.stop()
        self.reminder_timer.stop()
        event.accept()
        QApplication.instance().quit()
