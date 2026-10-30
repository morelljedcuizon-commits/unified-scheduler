"""Restrained, accessible light and dark palettes for native widgets."""
from PySide6.QtGui import QColor, QPalette


def apply_theme(app, theme="light"):
    dark = theme == "dark"
    c = {
        "bg": "#111b22" if dark else "#f4f7f9",
        "panel": "#19262f" if dark else "#ffffff",
        "text": "#e7eff3" if dark else "#172b3a",
        "muted": "#a2b4c1" if dark else "#617584",
        "line": "#30434f" if dark else "#e0e8ec",
        "hover": "#233a44" if dark else "#eaf3f1",
        "accent": "#66d3b5" if dark else "#087f68",
        "selection": "#244a43" if dark else "#e0f3ec",
    }
    palette = QPalette()
    for role, key in ((QPalette.Window, "bg"), (QPalette.WindowText, "text"),
                      (QPalette.Base, "panel"), (QPalette.AlternateBase, "bg"),
                      (QPalette.Text, "text"), (QPalette.Button, "panel"),
                      (QPalette.ButtonText, "text"), (QPalette.Highlight, "accent"),
                      (QPalette.PlaceholderText, "muted"), (QPalette.ToolTipBase, "panel"),
                      (QPalette.ToolTipText, "text")):
        palette.setColor(role, QColor(c[key]))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)
    app.setStyleSheet("""
        QWidget { color: %(text)s; font-family: 'Segoe UI'; font-size: 13px; }
        QMainWindow, QDialog, QWidget#page { background: %(bg)s; }
        QFrame#sidebar, QFrame#detail, QFrame#card, QWidget#surface { background: %(panel)s; }
        QFrame#sidebar { border-right: 1px solid %(line)s; }
        QFrame#card { border: 1px solid %(line)s; border-radius: 12px; }
        QFrame#detail { border-left: 1px solid %(line)s; }
        QLabel { background: transparent; }
        QLabel#muted { color: %(muted)s; }
        QLabel#eyebrow { color: %(accent)s; font-size: 11px; font-weight: 700; }
        QLabel#title { font-size: 28px; font-weight: 700; }
        QLabel#section { font-size: 15px; font-weight: 650; }
        QLabel#stat { font-size: 26px; font-weight: 700; }
        QLabel#logo { background: #087f68; color: white; border-radius: 11px; font-size: 25px; font-weight: 700; }
        QLabel#banner { background: %(selection)s; color: %(accent)s; padding: 9px; border-radius: 6px; }
        QPushButton { background: %(panel)s; border: 1px solid %(line)s; border-radius: 7px; padding: 8px 12px; font-weight: 600; }
        QPushButton:hover { background: %(hover)s; border-color: %(accent)s; }
        QPushButton:pressed { background: %(selection)s; }
        QPushButton:disabled { color: %(muted)s; }
        QPushButton#primary { background: #087f68; color: white; border: 1px solid #087f68; }
        QPushButton#primary:hover { background: #096d5b; }
        QPushButton#danger { color: #c44655; }
        QPushButton#nav { border: 0; text-align: left; padding: 12px 15px; background: transparent; }
        QPushButton#nav:checked { background: %(selection)s; color: %(accent)s; }
        QPushButton#nav:hover { background: %(hover)s; }
        QLineEdit, QTextEdit, QPlainTextEdit, QDateEdit, QTimeEdit, QSpinBox, QComboBox {
            background: %(panel)s; border: 1px solid %(line)s; border-radius: 6px; padding: 7px;
            selection-background-color: #087f68;
        }
        QLineEdit:focus, QTextEdit:focus, QComboBox:focus { border-color: %(accent)s; }
        QComboBox::drop-down { border: 0; width: 20px; }
        QComboBox QAbstractItemView { background: %(panel)s; selection-background-color: %(selection)s; }
        QScrollArea { background: transparent; border: 0; }
        QScrollArea > QWidget > QWidget { background: transparent; }
        QScrollBar:vertical { background: transparent; width: 9px; margin: 0; }
        QScrollBar::handle:vertical { background: %(line)s; border-radius: 4px; min-height: 25px; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
        QCheckBox { spacing: 8px; }
        QCheckBox::indicator { width: 16px; height: 16px; }
        QTableWidget, QListWidget { background: %(panel)s; border: 1px solid %(line)s; border-radius: 8px; gridline-color: %(line)s; }
        QTableWidget::item:selected, QListWidget::item:selected { background: %(selection)s; color: %(text)s; }
        QHeaderView::section { background: %(panel)s; border: 0; padding: 9px; color: %(muted)s; font-weight: 600; }
        QCalendarWidget QWidget { background: %(panel)s; }
        QCalendarWidget QToolButton { color: %(text)s; background: transparent; border: 0; padding: 5px; }
        QCalendarWidget QAbstractItemView { font-size: 11px; selection-background-color: #087f68; selection-color: white; }
        QToolTip { background: %(panel)s; color: %(text)s; border: 1px solid %(line)s; padding: 6px; }
        QStatusBar { color: %(muted)s; background: %(panel)s; border-top: 1px solid %(line)s; }
        QSplitter::handle { background: %(line)s; width: 1px; }
    """ % c)
    return c
