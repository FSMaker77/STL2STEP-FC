"""Qt stylesheet (dark, modern theme) for STL2STEP."""

ACCENT = "#4f8cff"
ACCENT_DARK = "#2f6bdb"
BG = "#14161c"
BG_PANEL = "#1c1f27"
BG_ELEV = "#232733"
FG = "#e6e9f0"
FG_MUTED = "#9aa3b5"
BORDER = "#2e3442"

QSS = f"""
* {{
    font-family: "Inter", "Segoe UI", "Ubuntu", "Noto Sans", sans-serif;
    font-size: 13px;
}}
QMainWindow, QWidget {{
    background-color: {BG};
    color: {FG};
}}
QToolTip {{
    background-color: {BG_ELEV};
    color: {FG};
    border: 1px solid {BORDER};
    padding: 4px;
}}
QMenuBar {{
    background-color: {BG_PANEL};
    border-bottom: 1px solid {BORDER};
}}
QMenuBar::item:selected {{ background-color: {BG_ELEV}; }}
QMenu {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER};
}}
QMenu::item:selected {{ background-color: {ACCENT}; color: white; }}

QPushButton {{
    background-color: {BG_ELEV};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 8px 16px;
    color: {FG};
}}
QPushButton:hover {{ background-color: #2b303d; }}
QPushButton:pressed {{ background-color: #333947; }}
QPushButton:disabled {{ color: {FG_MUTED}; background-color: {BG_PANEL}; }}
QPushButton#primary {{
    background-color: {ACCENT};
    border: 1px solid {ACCENT};
    color: white;
    font-weight: 600;
}}
QPushButton#primary:hover {{ background-color: {ACCENT_DARK}; }}
QPushButton#primary:disabled {{ background-color: #2b3650; color: #8fa0c0; border-color: #2b3650; }}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background-color: {BG_ELEV};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 8px;
    color: {FG};
    selection-background-color: {ACCENT};
}}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{
    background-color: {BG_ELEV};
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT};
}}
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    border: none; background: transparent; width: 14px;
}}

QListWidget, QPlainTextEdit {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: 6px;
    color: {FG};
}}
QListWidget::item {{ padding: 6px 8px; border-radius: 4px; }}
QListWidget::item:selected {{ background-color: {ACCENT}; color: white; }}
QListWidget::item:hover:!selected {{ background-color: #262b37; }}

QCheckBox {{ color: {FG}; spacing: 6px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px; border-radius: 4px;
    border: 1px solid {BORDER}; background-color: {BG_ELEV};
}}
QCheckBox::indicator:checked {{ background-color: {ACCENT}; border-color: {ACCENT}; }}

QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 8px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
    color: {FG_MUTED};
    font-weight: 600;
}}

QProgressBar {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: 6px;
    height: 14px;
    text-align: center;
    color: {FG};
}}
QProgressBar::chunk {{
    background-color: {ACCENT};
    border-radius: 5px;
}}

QScrollBar:vertical {{ background: {BG}; width: 10px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 5px; min-height: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}

QLabel#muted {{ color: {FG_MUTED}; }}
QLabel#title {{ font-size: 18px; font-weight: 700; }}
QLabel#subtitle {{ color: {FG_MUTED}; }}
QLabel#stat {{ color: {FG_MUTED}; font-size: 12px; }}
QLabel#statValue {{ font-weight: 600; }}
QSplitter::handle {{ background-color: {BORDER}; }}
"""
