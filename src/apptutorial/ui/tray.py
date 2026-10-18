"""System tray icon: capture indicator + pause toggle + capture/quit actions.

The tray is the always-visible capture indicator in v1 (green = listening, grey =
paused). See SPEC.md §10.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon


def _square_icon(color: str) -> QIcon:
    pix = QPixmap(64, 64)
    pix.fill(QColor(color))
    return QIcon(pix)


class TrayIcon(QObject):
    """Wraps a QSystemTrayIcon and exposes high-level signals."""

    capture_requested = Signal()
    pause_toggled = Signal(bool)
    quit_requested = Signal()

    def __init__(self, app: QApplication, hotkey: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._hotkey = hotkey
        self._active_icon = _square_icon("#2e7d32")  # green: listening
        self._paused_icon = _square_icon("#9e9e9e")  # grey: paused
        self._tray = QSystemTrayIcon(self._active_icon, self)

        menu = QMenu()

        capture = QAction(f"Capture active window  ({hotkey})", menu)
        capture.triggered.connect(lambda: self.capture_requested.emit())
        menu.addAction(capture)

        capture_delayed = QAction("Capture in 3s (for testing)", menu)
        capture_delayed.triggered.connect(self._capture_delayed)
        menu.addAction(capture_delayed)

        menu.addSeparator()
        self._pause_action = QAction("Pause capture", menu)
        self._pause_action.setCheckable(True)
        self._pause_action.toggled.connect(self.pause_toggled)
        menu.addAction(self._pause_action)

        menu.addSeparator()
        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(lambda: self.quit_requested.emit())
        menu.addAction(quit_action)

        self._tray.setContextMenu(menu)
        self.set_paused(False)

    def _capture_delayed(self) -> None:
        self.notify("appTutorial", "Capturing in 3 seconds - focus the window you want.")
        QTimer.singleShot(3000, self.capture_requested.emit)

    def set_paused(self, paused: bool) -> None:
        self._tray.setIcon(self._paused_icon if paused else self._active_icon)
        self._tray.setToolTip(
            "appTutorial - paused" if paused else f"appTutorial - listening ({self._hotkey})"
        )
        self._pause_action.blockSignals(True)
        self._pause_action.setChecked(paused)
        self._pause_action.blockSignals(False)

    def notify(self, title: str, message: str) -> None:
        self._tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 3000)

    def show(self) -> None:
        self._tray.show()
