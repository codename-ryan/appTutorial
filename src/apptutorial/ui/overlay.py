"""See-through highlight overlay marking where to focus for the current step.

A frameless, always-on-top, click-through window that draws a soft, gently pulsing frame around
the step's target (a ribbon control via UIA, or a cell via Excel COM). It never steals focus and
is excluded from screen capture, so clicks pass through to the app and the frame never appears in
the screenshots we send to the models. Target boxes arrive in physical pixels and the window is
placed with Win32 SetWindowPos (physical), bypassing Qt's logical-coordinate/DPI transform so it
lines up exactly under mixed-DPI / multi-monitor setups (SPEC.md §6, §9).
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

_ACCENT = QColor("#16A34A")  # vivid green frame


class HighlightOverlay(QWidget):
    _MARGIN = 7  # physical px of breathing room around the target box

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

        # Gentle "breathing" pulse to draw the eye without being distracting.
        self._pulse = QPropertyAnimation(self, b"windowOpacity", self)
        self._pulse.setDuration(1400)
        self._pulse.setStartValue(1.0)
        self._pulse.setKeyValueAt(0.5, 0.55)
        self._pulse.setEndValue(1.0)
        self._pulse.setLoopCount(-1)
        self._pulse.setEasingCurve(QEasingCurve.Type.InOutSine)

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
        if self._pulse.state() != QPropertyAnimation.State.Running:
            self._pulse.start()
        self.update()

    def hide_box(self) -> None:
        self._pulse.stop()
        self.setWindowOpacity(1.0)
        self.hide()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        frame = self.rect().adjusted(5, 5, -5, -5)
        glow = QColor(_ACCENT)
        glow.setAlpha(55)
        painter.setPen(QPen(glow, 8))
        painter.drawRoundedRect(frame, 10, 10)
        painter.setPen(QPen(_ACCENT, 2.5))
        painter.drawRoundedRect(frame, 10, 10)
