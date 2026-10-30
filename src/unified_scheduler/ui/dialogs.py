"""Accessible forms for local entries and private subscription setup."""
from datetime import date, datetime, time, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from PySide6.QtCore import QDate, QTime, Qt, QThreadPool
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDateEdit, QDialog, QDialogButtonBox,
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QScrollArea, QTextEdit, QTimeEdit, QVBoxLayout, QWidget,
)
from unified_scheduler.models import Event
from unified_scheduler.ui.workers import Worker

REMINDERS = [("Off", -1), ("At time", 0), ("5 minutes before", 5),
             ("15 minutes before", 15), ("30 minutes before", 30),
             ("1 hour before", 60), ("1 day before", 1440)]


def text_label(text, name=None):
    label = QLabel(text)
    label.setTextFormat(Qt.PlainText)
    label.setWordWrap(True)
    if name:
        label.setObjectName(name)
    return label


def reminder_combo(value=30):
    combo = QComboBox()
    for label, minutes in REMINDERS:
        combo.addItem(label, minutes)
    combo.setCurrentIndex(max(0, combo.findData(-1 if value is None else value)))
    return combo


class TaskDialog(QDialog):
    def __init__(self, parent, timezone, event=None, selected_date=None, default_reminder=30):
        super().__init__(parent)
        self.zone = ZoneInfo(timezone)
        self.original_event = event
        self.result_event = None
        self.color_value = event.color if event and event.color else "#087f68"
        self.setWindowTitle("Edit local entry" if event else "Create an entry")
        self.setMinimumWidth(520)
        self.resize(570, 710)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 22)
        layout.setSpacing(14)
        layout.addWidget(text_label("Make room for what matters", "section"))
        layout.addWidget(text_label("Saved on this device. Available offline.", "muted"))
        form = QFormLayout()
        form.setSpacing(10)
        self.title_edit = QLineEdit(event.title if event else "")
        self.title_edit.setPlaceholderText("What needs to get done?")
        self.title_edit.setMaxLength(500)
        self.kind = QComboBox()
        self.kind.addItems(["Task", "Event"])
        self.kind.setCurrentText("Task" if not event or event.kind == "task" else "Event")
        self.description = QTextEdit()
        self.description.setAcceptRichText(False)
        self.description.setPlainText(event.description if event else "")
        self.description.setMaximumHeight(85)
        now = datetime.now(self.zone)
        start = self._parse(event.start) if event else datetime.combine(selected_date or now.date(), time(9), self.zone)
        end = self._parse(event.end) if event else start + timedelta(hours=1)
        self.start_date = QDateEdit(QDate(start.year, start.month, start.day))
        self.end_date = QDateEdit(QDate(end.year, end.month, end.day))
        for field in (self.start_date, self.end_date):
            field.setCalendarPopup(True)
            field.setDisplayFormat("ddd, dd MMM yyyy")
        self.start_time = QTimeEdit(QTime(start.hour, start.minute))
        self.end_time = QTimeEdit(QTime(end.hour, end.minute))
        self.start_time.setDisplayFormat("h:mm AP")
        self.end_time.setDisplayFormat("h:mm AP")
        self.all_day = QCheckBox("All day / date-only deadline")
        self.all_day.setChecked(bool(event and event.all_day))
        if event and event.all_day:
            self.end_date.setDate(self.end_date.date().addDays(-1))
        self.priority = QComboBox()
        self.priority.addItems(["Low", "Medium", "High"])
        self.priority.setCurrentText(event.priority if event else "Medium")
        self.status = QComboBox()
        self.status.addItems(["Pending", "In Progress", "Completed"])
        self.status.setCurrentText(event.status if event else "Pending")
        self.recurrence = QComboBox()
        for label, rule in (("Does not repeat", ""), ("Daily", "daily"), ("Weekly", "weekly"), ("Monthly", "monthly")):
            self.recurrence.addItem(label, rule)
        self.recurrence.setCurrentIndex(max(0, self.recurrence.findData(event.recurrence if event else "")))
        self.reminder = reminder_combo(event.reminder_minutes if event else default_reminder)
        self.category = QLineEdit(event.category if event else "")
        self.category.setPlaceholderText("Study, Personal, Work…")
        self.location = QLineEdit(event.location if event else "")
        self.color = QPushButton("Choose color")
        self.color.clicked.connect(self.choose_color)
        self._color_style()
        form.addRow("Title *", self.title_edit)
        form.addRow("Type", self.kind)
        form.addRow("Description", self.description)
        form.addRow("Start / due date", self.start_date)
        form.addRow("Start / due time", self.start_time)
        form.addRow("", self.all_day)
        form.addRow("End date (inclusive for all-day)", self.end_date)
        form.addRow("End time (events)", self.end_time)
        form.addRow("Priority", self.priority)
        form.addRow("Status", self.status)
        form.addRow("Repeat", self.recurrence)
        form.addRow("Reminder", self.reminder)
        form.addRow("Category", self.category)
        form.addRow("Color", self.color)
        form.addRow("Location", self.location)
        fields = QWidget()
        fields.setLayout(form)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(fields)
        layout.addWidget(scroll, 1)
        self.error = text_label("", "muted")
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setObjectName("primary")
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.all_day.toggled.connect(self._update_fields)
        self.kind.currentIndexChanged.connect(self._update_fields)
        self.start_date.dateChanged.connect(self._align_end)
        self._update_fields()

    def _parse(self, value):
        dt = datetime.fromisoformat(value)
        return dt.replace(tzinfo=self.zone) if dt.tzinfo is None else dt.astimezone(self.zone)

    def _align_end(self):
        if self.end_date.date() < self.start_date.date():
            self.end_date.setDate(self.start_date.date())

    def _update_fields(self):
        self.start_time.setEnabled(not self.all_day.isChecked())
        task = self.kind.currentText() == "Task"
        self.end_date.setEnabled(not task)
        self.end_time.setEnabled(not self.all_day.isChecked() and not task)

    def _color_style(self):
        self.color.setStyleSheet(f"border-left: 5px solid {self.color_value};")

    def choose_color(self):
        from PySide6.QtGui import QColor
        color = QColorDialog.getColor(QColor(self.color_value), self)
        if color.isValid():
            self.color_value = color.name()
            self._color_style()

    def save(self):
        title = self.title_edit.text().strip()
        if not title:
            self.error.setText("Give this entry a title.")
            self.title_edit.setFocus()
            return
        start_date = self.start_date.date().toPython()
        end_date = self.end_date.date().toPython()
        is_task = self.kind.currentText() == "Task"
        if self.all_day.isChecked():
            start = start_date.isoformat()
            end = ((start_date if is_task else end_date) + timedelta(days=1)).isoformat()
        else:
            start_dt = datetime.combine(start_date, self.start_time.time().toPython(), self.zone)
            end_dt = start_dt if is_task else datetime.combine(end_date, self.end_time.time().toPython(), self.zone)
            # A round trip detects nonexistent wall times during a spring DST jump.
            from datetime import timezone
            if any(dt.astimezone(timezone.utc).astimezone(self.zone).replace(tzinfo=None) != dt.replace(tzinfo=None)
                   for dt in (start_dt, end_dt)):
                self.error.setText("That time falls in a daylight-saving clock change. Choose a valid time.")
                return
            start, end = start_dt.isoformat(), end_dt.isoformat()
        if end < start or (not is_task and not self.all_day.isChecked() and end == start):
            self.error.setText("The end must be after the start.")
            return
        identifier = self.original_event.id if self.original_event else "local:" + uuid4().hex
        self.result_event = Event(
            id=identifier, source="local", account_id="local", calendar_id="local", uid=identifier,
            title=title, start=start, end=end, all_day=self.all_day.isChecked(),
            description=self.description.toPlainText(), location=self.location.text().strip(),
            kind="task" if is_task else "event", priority=self.priority.currentText(),
            status=self.status.currentText(), recurrence=self.recurrence.currentData(),
            reminder_minutes=None if self.reminder.currentData() < 0 else self.reminder.currentData(),
            category=self.category.text().strip(), color=self.color_value,
            timezone=str(self.zone),
        )
        self.accept()


class MoodleDialog(QDialog):
    """URL never appears after save, in a tooltip, or in transport diagnostics."""
    def __init__(self, parent, provider, timezone, account=None, color="#b06a24"):
        super().__init__(parent)
        self.provider, self.timezone, self.account = provider, timezone, account
        self.color_value = color
        self.worker = None
        self.setWindowTitle("Edit Moodle calendar" if account else "Add Moodle calendar")
        self.setMinimumWidth(500)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)
        layout.addWidget(text_label("Your academic deadlines, together", "section"))
        layout.addWidget(text_label("In Moodle, open Calendar → Export calendar. Choose My personal events and the Recent and next 60 days time period, then copy the calendar URL. No Moodle password is needed.", "muted"))
        form = QFormLayout()
        self.name_edit = QLineEdit(account.label if account else "")
        self.name_edit.setPlaceholderText("e.g. MSU-IIT MOLE")
        self.url_edit = QLineEdit()
        self.url_edit.setEchoMode(QLineEdit.Password)
        self.url_edit.setPlaceholderText("Leave blank to keep saved URL" if account else "https://…/calendar/export_execute.php?…")
        self.url_edit.setMaxLength(16000)
        form.addRow("Calendar name", self.name_edit)
        form.addRow("Private ICS URL", self.url_edit)
        color_button = QPushButton("Choose source color")
        color_button.clicked.connect(self.choose_color)
        form.addRow("Color", color_button)
        layout.addLayout(form)
        layout.addWidget(text_label("The private URL is stored in Windows Credential Manager. The URL's export range controls which deadlines Moodle shares.", "muted"))
        self.message = text_label("")
        layout.addWidget(self.message)
        row = QHBoxLayout()
        self.test = QPushButton("Test connection")
        self.test.clicked.connect(self.test_connection)
        row.addWidget(self.test)
        row.addStretch()
        self.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.save)
        self.buttons.rejected.connect(self.reject)
        self.buttons.button(QDialogButtonBox.Save).setObjectName("primary")
        row.addWidget(self.buttons)
        layout.addLayout(row)

    def choose_color(self):
        from PySide6.QtGui import QColor
        color = QColorDialog.getColor(QColor(self.color_value), self)
        if color.isValid():
            self.color_value = color.name()

    def test_connection(self):
        url = self.url_edit.text().strip()
        if not url:
            self.message.setText("Enter the URL to test it. A blank URL preserves an existing subscription.")
            return
        from unified_scheduler.sync import sync_window
        start, end, timezone = sync_window(self.provider.repo)
        self._run(lambda: self.provider.inspect_feed(url, start, end, timezone),
                  lambda inspection: self.message.setText(inspection.message))

    def _run(self, function, callback):
        self.test.setEnabled(False)
        self.buttons.setEnabled(False)
        self.message.setText("Connecting securely…")
        self.worker = Worker(function)
        self.worker.signals.succeeded.connect(callback)
        self.worker.signals.failed.connect(self.message.setText)
        self.worker.signals.finished.connect(self._finished)
        QThreadPool.globalInstance().start(self.worker)

    def _finished(self):
        self.test.setEnabled(True)
        self.buttons.setEnabled(True)
        self.worker = None

    def save(self):
        name, url = self.name_edit.text().strip(), self.url_edit.text().strip()
        if not name or (not self.account and not url):
            self.message.setText("Enter a calendar name and its private HTTPS URL.")
            return
        function = (lambda: self.provider.edit_feed(self.account.id, name, url or None, self.color_value)) if self.account else (
            lambda: self.provider.add_feed(name, url, self.color_value))
        self._run(function, lambda _: self.accept())

    def reject(self):
        if self.worker is None:
            super().reject()


class WelcomeDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.choice = "local"
        self.setWindowTitle("Welcome to Unified Scheduler")
        self.setMinimumWidth(490)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 32, 36, 32)
        layout.setSpacing(18)
        layout.addWidget(text_label("A little clarity for your day.", "title"))
        layout.addWidget(text_label("Your tasks, calendar and academic deadlines in one quiet place. Start locally, or connect your calendars when you're ready.", "muted"))
        for title, choice in (("Connect Google account", "google"), ("Add Moodle calendar", "moodle"), ("Continue with local calendar", "local")):
            button = QPushButton(title)
            if choice == "local":
                button.setObjectName("primary")
            button.clicked.connect(lambda checked=False, c=choice: self.choose(c))
            layout.addWidget(button)
        layout.addWidget(text_label("Private by default. No custom cloud account or subscription.", "muted"))

    def choose(self, choice):
        self.choice = choice
        self.accept()
