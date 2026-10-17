"""Application entry point."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QSurfaceFormat
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow
from .theme import QSS
from ..version import APP_NAME


def main() -> int:
    QSurfaceFormat.setDefaultFormat(QSurfaceFormat())
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("STL2STEP")
    app.setStyle("Fusion")
    app.setFont(QFont("Inter", 10))
    app.setStyleSheet(QSS)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
