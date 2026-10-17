"""System tray icon.

M0: a minimal tray with a Quit action. M1 adds the capture indicator and pause toggle.
"""

from __future__ import annotations

from PySide6.QtGui import QAction, QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon


def _placeholder_icon() -> QIcon:
    """A plain icon until a real asset is added (M1)."""
    pix = QPixmap(64, 64)
    pix.fill()  # opaque white
    return QIcon(pix)


def build_tray(app: QApplication) -> QSystemTrayIcon:
    tray = QSystemTrayIcon(_placeholder_icon(), app)
    tray.setToolTip("appTutorial")

    menu = QMenu()
    quit_action = QAction("Quit", menu)
    quit_action.triggered.connect(app.quit)
    menu.addAction(quit_action)
    tray.setContextMenu(menu)

    return tray
