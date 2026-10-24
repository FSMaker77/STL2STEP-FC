"""Application entry point."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPixmap, QSurfaceFormat
from PySide6.QtWidgets import QApplication, QWidget

from .theme import QSS
from ..version import APP_NAME, __version__

# Keep the splash on screen long enough to be readable, but never add delay to
# a cold start (which already takes longer than this).
_MIN_SPLASH_SECONDS = 0.7


def configure_surface_format() -> None:
    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    fmt.setDepthBufferSize(24)
    fmt.setSamples(4)
    QSurfaceFormat.setDefaultFormat(fmt)


def _splash_pixmap() -> QPixmap | None:
    path = Path(__file__).resolve().parent.parent / "data" / "splash.png"
    pixmap = QPixmap(str(path))
    if pixmap.isNull():
        return None

    # Never let the splash cover the whole screen on small/high-DPI displays.
    screen = QGuiApplication.primaryScreen()
    if screen is not None:
        available = screen.availableGeometry()
        max_width = int(available.width() * 0.8)
        max_height = int(available.height() * 0.8)
        if pixmap.width() > max_width or pixmap.height() > max_height:
            pixmap = pixmap.scaled(
                max_width,
                max_height,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
    return pixmap


class _SplashScreen(QWidget):
    """Lightweight splash screen.

    QSplashScreen is not used on purpose: its Show handler calls
    waitForWidgetMapped() with a 1 s timeout, which on Windows always hits the
    timeout and delays startup by one second (qsplashscreen.cpp).  This widget
    only paints the image and a status line.
    """

    def __init__(self, pixmap: QPixmap, message: str):
        super().__init__(None, Qt.SplashScreen | Qt.FramelessWindowHint)
        self._pixmap = pixmap
        self._message = message
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setCursor(Qt.BusyCursor)
        self.setFixedSize(pixmap.size())

        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            self.move(screen.availableGeometry().center() - self.rect().center())

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.drawPixmap(0, 0, self._pixmap)
        painter.setPen(QColor("#c9d4e5"))
        painter.drawText(
            self.rect().adjusted(8, 8, -8, -8),
            Qt.AlignBottom | Qt.AlignLeft,
            self._message,
        )

    def mousePressEvent(self, _event) -> None:  # noqa: N802
        self.hide()


def main() -> int:
    configure_surface_format()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("STL2STEP")
    app.setStyle("Fusion")
    app.setFont(QFont("Inter", 10))
    app.setStyleSheet(QSS)

    # Show the splash before importing the main window: that import is the
    # slowest part of a cold start (Qt/OpenGL widgets and NumPy).
    splash = None
    splash_started = time.perf_counter()
    pixmap = _splash_pixmap()
    if pixmap is not None:
        splash = _SplashScreen(pixmap, f"Versione {__version__}  -  caricamento...")
        splash.show()
        app.processEvents()

    from .main_window import MainWindow

    window = MainWindow()
    window.show()
    app.processEvents()
    if splash is not None:
        remaining_ms = int((_MIN_SPLASH_SECONDS - (time.perf_counter() - splash_started)) * 1000)
        if remaining_ms > 0:
            QTimer.singleShot(remaining_ms, splash.close)
        else:
            splash.close()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
