"""Event rows and useful native day, week and month calendar views."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from PySide6.QtCore import Qt, Signal, QDate
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFrame, QHBoxLayout, QHeaderView,
    QLabel, QListWidget, QListWidgetItem, QPushButton, QTableWidget,
    QVBoxLayout, QWidget,
)
from unified_scheduler.timeutils import event_start, event_end
from unified_scheduler.ui.dialogs import text_label

SOURCE_COLORS = {"local": "#087f68", "google": "#3b78cf", "moodle": "#b06a24"}
SOURCE_NAMES = {"local": "Local", "google": "Google", "moodle": "Moodle"}


def time_caption(event, timezone, include_date=False):
    start, end = event_start(event, timezone), event_end(event, timezone)
    prefix = start.strftime("%d %b · ") if include_date else ""
    if event.all_day:
        last = end.date() - timedelta(days=1)
        suffix = f" · through {last:%d %b}" if last > start.date() else ""
        return prefix + "All day" + suffix
    clock = start.strftime("%I:%M %p").lstrip("0")
    if event.kind != "task" and end > start:
        clock += " – " + end.strftime("%I:%M %p").lstrip("0")
    return prefix + clock


class EventRow(QFrame):
    selected = Signal(object)
    completionChanged = Signal(object, bool)

    def __init__(self, event, timezone, calendar_name="", color="", show_date=False):
        super().__init__()
        self.entry = event
        self.setObjectName("card")
        self.setMinimumHeight(82)
        row = QHBoxLayout(self)
        row.setContentsMargins(15, 11, 15, 11)
        row.setSpacing(14)
        accent = QFrame()
        accent.setFixedWidth(4)
        chosen_color = color or event.color or SOURCE_COLORS.get(event.source, "#087f68")
        # Source content is untrusted; only QColor-valid colors enter styles.
        safe_color = QColor(chosen_color).name() if QColor(chosen_color).isValid() else "#087f68"
        accent.setStyleSheet(f"background: {safe_color}; border-radius: 2px;")
        row.addWidget(accent)
        complete = QCheckBox()
        complete.setAccessibleName("Mark complete: " + event.title)
        complete.setChecked(event.status == "Completed")
        complete.setToolTip("Track completion locally")
        complete.toggled.connect(lambda checked: self.completionChanged.emit(event, checked))
        row.addWidget(complete)
        text = QVBoxLayout()
        text.setSpacing(5)
        title = text_label(event.title)
        title.setStyleSheet("font-weight: 600;" + ("text-decoration: line-through;" if event.status == "Completed" else ""))
        text.addWidget(title)
        metadata = SOURCE_NAMES.get(event.source, event.source) + (f" · {calendar_name}" if calendar_name and calendar_name != "Local" else "")
        if event.category:
            metadata += " · " + event.category
        if event.priority == "High":
            metadata += " · High priority"
        text.addWidget(text_label(metadata, "muted"))
        row.addLayout(text, 1)
        when = text_label(time_caption(event, timezone, show_date), "muted")
        when.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        when.setMaximumWidth(175)
        when.setMinimumWidth(130)
        row.addWidget(when)
        self.setCursor(Qt.PointingHandCursor)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.selected.emit(self.entry)
        super().mouseReleaseEvent(event)


class CalendarView(QWidget):
    eventSelected = Signal(object)
    rangeChanged = Signal()
    dateSelected = Signal(object)

    def __init__(self):
        super().__init__()
        self.anchor = date.today()
        self.mode = "Month"
        self.events = []
        self.timezone = "Asia/Manila"
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        toolbar = QHBoxLayout()
        previous, following, today = QPushButton("‹"), QPushButton("›"), QPushButton("Today")
        previous.setAccessibleName("Previous calendar period")
        following.setAccessibleName("Next calendar period")
        previous.setFixedWidth(36)
        following.setFixedWidth(36)
        previous.clicked.connect(lambda: self.shift(-1))
        following.clicked.connect(lambda: self.shift(1))
        today.clicked.connect(self.jump_today)
        toolbar.addWidget(previous)
        toolbar.addWidget(following)
        toolbar.addWidget(today)
        self.period = text_label("", "section")
        toolbar.addWidget(self.period, 1)
        self.mode_box = QComboBox()
        self.mode_box.addItems(["Day", "Week", "Month", "Agenda"])
        self.mode_box.setCurrentText("Month")
        self.mode_box.currentTextChanged.connect(self.change_mode)
        toolbar.addWidget(self.mode_box)
        layout.addLayout(toolbar)
        self.table = QTableWidget()
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        self.table.cellDoubleClicked.connect(self.select_cell_date)
        layout.addWidget(self.table, 1)

    def range(self):
        if self.mode == "Day":
            return self.anchor, self.anchor + timedelta(days=1)
        if self.mode == "Week":
            start = self.anchor - timedelta(days=self.anchor.weekday())
            return start, start + timedelta(days=7)
        if self.mode == "Month":
            first = self.anchor.replace(day=1)
            start = first - timedelta(days=first.weekday())
            return start, start + timedelta(days=42)
        return self.anchor, self.anchor + timedelta(days=30)

    def change_mode(self, mode):
        self.mode = mode
        self.rangeChanged.emit()

    def set_date(self, day):
        self.anchor = day
        self.rangeChanged.emit()

    def shift(self, direction):
        if self.mode == "Month":
            q = QDate(self.anchor.year, self.anchor.month, self.anchor.day).addMonths(direction)
            self.anchor = q.toPython()
        else:
            self.anchor += timedelta(days=direction * {"Day": 1, "Week": 7, "Agenda": 30}[self.mode])
        self.rangeChanged.emit()

    def jump_today(self):
        from zoneinfo import ZoneInfo
        self.set_date(datetime.now(ZoneInfo(self.timezone)).date())

    def select_cell_date(self, row, column):
        start, _ = self.range()
        day = start + timedelta(days=row * 7 + column) if self.mode == "Month" else start + timedelta(days=column)
        self.dateSelected.emit(day)

    def render(self, events, timezone, colors):
        self.events, self.timezone = events, timezone
        start, end = self.range()
        self.period.setText(self.anchor.strftime("%B %Y") if self.mode == "Month" else f"{start:%d %b} – {end - timedelta(days=1):%d %b %Y}")
        self.table.clear()
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.Interactive)
        if self.mode == "Month":
            self.table.setRowCount(6)
            self.table.setColumnCount(7)
            self.table.setHorizontalHeaderLabels(["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"])
            self.table.verticalHeader().setSectionResizeMode(QHeaderView.Stretch)
            for index in range(42):
                day = start + timedelta(days=index)
                cell = QWidget()
                box = QVBoxLayout(cell)
                box.setContentsMargins(5, 4, 5, 4)
                box.setSpacing(2)
                number = text_label(day.strftime("%d") + (" · Today" if day == datetime.now(ZoneInfo(timezone)).date() else ""),
                                    "eyebrow" if day.month == self.anchor.month else "muted")
                box.addWidget(number)
                listing = self.event_list(self.for_day(day), colors, compact=True)
                box.addWidget(listing, 1)
                self.table.setCellWidget(index // 7, index % 7, cell)
                self.table.setRowHeight(index // 7, 95)
        elif self.mode == "Agenda":
            self.table.setRowCount(1)
            self.table.setColumnCount(1)
            self.table.setHorizontalHeaderLabels(["NEXT 30 DAYS"])
            self.table.verticalHeader().setSectionResizeMode(QHeaderView.Stretch)
            self.table.setCellWidget(0, 0, self.event_list(events, colors, dated=True))
        else:
            days = 1 if self.mode == "Day" else 7
            self.table.setRowCount(25)
            self.table.setColumnCount(days)
            self.table.setHorizontalHeaderLabels([(start + timedelta(days=d)).strftime("%a %d") for d in range(days)])
            self.table.verticalHeader().show()
            self.table.setVerticalHeaderLabels(["All day"] + [f"{hour:02d}:00" for hour in range(24)])
            for row in range(25):
                self.table.setRowHeight(row, 68 if row else 78)
            first_hour = 8
            for column in range(days):
                day = start + timedelta(days=column)
                daily = self.for_day(day)
                for row in range(25):
                    matching = [e for e in daily if (e.all_day and row == 0) or (
                        not e.all_day and row > 0 and (event_start(e, timezone).hour if event_start(e, timezone).date() == day else 0) == row - 1)]
                    if matching:
                        self.table.setCellWidget(row, column, self.event_list(matching, colors, compact=True))
                        if row > 0:
                            first_hour = min(first_hour, row - 1)
            self.table.scrollTo(self.table.model().index(first_hour + 1, 0), QAbstractItemView.PositionAtTop)

    def for_day(self, day):
        return [event for event in self.events if event_start(event, self.timezone).date() <= day and
                (event_end(event, self.timezone).date() > day or
                 event_end(event, self.timezone).date() == day and
                 (not event.all_day and (event_end(event, self.timezone).time().isoformat() != "00:00:00" or
                                         event_start(event, self.timezone) == event_end(event, self.timezone))))]

    def event_list(self, events, colors, compact=False, dated=False):
        listing = QListWidget()
        listing.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        listing.setStyleSheet("QListWidget { border: 0; border-radius: 0; background: transparent; } QListWidget::item { padding: 5px 3px; }")
        listing.setWordWrap(True)
        for event in events:
            caption = time_caption(event, self.timezone, dated)
            text = ("✓ " if event.status == "Completed" else "") + event.title
            text = ("● " + text + "\n" + caption) if not compact else (("All day" if event.all_day else event_start(event, self.timezone).strftime("%H:%M")) + "  " + text)
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, event)
            color = event.color or colors.get(event.calendar_id, SOURCE_COLORS.get(event.source, "#087f68"))
            item.setForeground(QColor(color))
            item.setToolTip(event.title + "\n" + caption + "\n" + SOURCE_NAMES.get(event.source, event.source))
            listing.addItem(item)
        if not events and dated:
            item = QListWidgetItem("Nothing scheduled here. Add a task or connect a calendar.")
            item.setFlags(Qt.NoItemFlags)
            listing.addItem(item)
        listing.itemClicked.connect(lambda item: self.eventSelected.emit(item.data(Qt.UserRole)) if item.data(Qt.UserRole) else None)
        return listing
