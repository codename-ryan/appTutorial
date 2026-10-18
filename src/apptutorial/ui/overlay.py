"""See-through highlight overlay marking where to focus for the current step.

A frameless, always-on-top, click-through window that draws a glowing frame around the step's
target (a ribbon control via UIA, or a cell via Excel COM). It never steals focus and is
excluded from screen capture, so clicks pass through to the app and the frame never appears in
the screenshots we send to the models. Target boxes arrive in physical pixels and the window is
placed with Win32 SetWindowPos (physical), bypassing Qt's logical-coordinate/DPI transform so
it lines up exactly under mixed-DPI / multi-monitor setups (SPEC.md §6, §9).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

_ACCENT = QColor("#1a73e8")  # vivid blue frame


class HighlightOverlay(QWidget):
    _MARGIN = 6  # logical px of breathing room around the target box

    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput  # click-through
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self._capture_excluded = False

    def show_box(self, rect_physical: tuple[int, int, int, int]) -> None:
        """Frame a target given its screen box in physical pixels (placed via Win32, exactly)."""
        from apptutorial.capture.window import exclude_from_capture, move_window_physical

        left, top, width, height = rect_physical
        x = left - self._MARGIN
        y = top - self._MARGIN
        w = width + 2 * self._MARGIN
        h = height + 2 * self._MARGIN
        self.show()  # ensure the native window exists before we move it
        if not self._capture_excluded:
            self._capture_excluded = exclude_from_capture(int(self.winId()))
        move_window_physical(int(self.winId()), x, y, w, h)
        self.update()

    def hide_box(self) -> None:
        self.hide()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Soft outer halo, then the crisp frame.
        halo = QColor(_ACCENT)
        halo.setAlpha(70)
        painter.setPen(QPen(halo, 7))
        painter.drawRoundedRect(self.rect().adjusted(4, 4, -4, -4), 9, 9)
        painter.setPen(QPen(_ACCENT, 3))
        painter.drawRoundedRect(self.rect().adjusted(4, 4, -4, -4), 9, 9)
