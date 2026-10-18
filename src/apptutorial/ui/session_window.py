"""The main session window: capture -> identify -> tutorial menu -> interactive steps.

A compact, frameless, always-on-top card docked to the top-right corner. It floats above the
app you're working in (so it doesn't vanish when that app takes focus) and stays until you
close it with the X. Draggable by its header. The screenshot is never shown or saved here.
In M5 the plan view is the interactive one-step-at-a-time panel (StepPanel) that the
orchestrator drives as it verifies each step against the live screen.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from apptutorial.ui.menu import TutorialMenu
from apptutorial.ui.panel import StepPanel

if TYPE_CHECKING:
    from apptutorial.ai.schemas import AppIdentification, TutorialStep
    from apptutorial.capture.backend import Screenshot, WindowInfo

_STYLE = """
QFrame#card { background: #ffffff; border-radius: 14px; }
QLabel { color: #1f2328; font-size: 13px; }
QLabel#title { color: #2e7d32; font-weight: 600; font-size: 14px; }
QLabel#status { color: #6a737d; }
QLabel#progress { color: #8a929b; font-size: 12px; }
QLabel#instruction { color: #1f2328; font-size: 15px; font-weight: 600; }
QLabel#doneWhen { color: #2e7d32; }
QLabel#why { color: #57606a; font-style: italic; }
QLabel#hint { color: #8a6d00; background: #fff6d6; border: 1px solid #f0e2a8;
              border-radius: 8px; padding: 6px 8px; }
QLabel#stepStatus { color: #8a929b; font-size: 12px; }
QPushButton { background: #f3f4f6; border: 1px solid #e2e4e8; border-radius: 8px;
              padding: 7px 10px; color: #1f2328; }
QPushButton:hover { background: #e9ebef; }
QPushButton:disabled { color: #b0b6bd; }
QPushButton:checked { background: #e4ecff; border-color: #c2d4ff; }
QPushButton#tutorialBtn { text-align: left; }
QPushButton#close { background: transparent; border: none; color: #6a737d; font-size: 15px; }
QPushButton#close:hover { background: #eceef1; border-radius: 13px; color: #1f2328; }
QLineEdit { background: #ffffff; color: #1f2328; border: 1px solid #d0d7de;
            border-radius: 8px; padding: 6px 8px; }
"""


class SessionWindow(QWidget):
    goal_chosen = Signal(str)
    next_clicked = Signal()
    back_clicked = Signal()
    closed = Signal()
    _HEADER_BAND = 48  # top strip (px) that acts as a drag handle

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("appTutorial")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        # Never grab the foreground when shown, so capturing the "active window" keeps
        # targeting the app being taught (e.g. Excel), not this card.
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.resize(360, 540)
        self._placed = False
        self._drag_offset = None
        self._app_name = ""
        self._capture_excluded = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)  # room for the drop shadow

        card = QFrame()
        card.setObjectName("card")
        outer.addWidget(card)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setXOffset(0)
        shadow.setYOffset(6)
        shadow.setColor(QColor(0, 0, 0, 90))
        card.setGraphicsEffect(shadow)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 10, 12, 14)
        layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("appTutorial")
        title.setObjectName("title")
        close_btn = QPushButton(chr(0x2715))  # heavy multiplication X
        close_btn.setObjectName("close")
        close_btn.setFixedSize(26, 26)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self._close)
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(close_btn)
        layout.addLayout(header)

        self._appline = QLabel()
        self._appline.setWordWrap(True)
        self._appline.setTextFormat(Qt.TextFormat.RichText)
        self._status = QLabel()
        self._status.setObjectName("status")
        self._status.setWordWrap(True)
        self._menu = TutorialMenu()
        self._menu.goal_chosen.connect(self.goal_chosen)

        self._panel = StepPanel()
        self._panel.next_clicked.connect(self.next_clicked)
        self._panel.back_clicked.connect(self.back_clicked)

        layout.addWidget(self._appline)
        layout.addWidget(self._status)
        layout.addWidget(self._menu)
        layout.addWidget(self._panel, 1)

        self.setStyleSheet(_STYLE)
        self._menu.hide()
        self._panel.hide()

    # --- frameless window dragging (via the header strip) -------------------------------
    def mousePressEvent(self, event) -> None:
        if (
            event.button() == Qt.MouseButton.LeftButton
            and event.position().y() <= self._HEADER_BAND
        ):
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        else:
            self._drag_offset = None

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        self._drag_offset = None

    def _close(self) -> None:
        self.hide()
        self.closed.emit()  # let the controller stop any running step/verify loop

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Keep the tutor card out of every screenshot we take of the target app.
        if not self._capture_excluded:
            from apptutorial.capture.window import exclude_from_capture

            self._capture_excluded = exclude_from_capture(int(self.winId()))
            print(f"[window] hidden from screen capture: {self._capture_excluded}", flush=True)

    # --- placement / show ---------------------------------------------------------------
    def _place_top_right(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        self.move(geo.right() - self.width() - 24, geo.top() + 24)

    def _raise(self) -> None:
        if not self._placed:
            self._place_top_right()
            self._placed = True
        self.show()
        self.raise_()  # no activateWindow(): stay visible without stealing focus from the app

    # --- state updates ------------------------------------------------------------------
    def set_status(self, text: str) -> None:
        self._status.setText(text)

    def show_analyzing(self, window: WindowInfo, screenshot: Screenshot) -> None:
        self._appline.setText(f"<b>Analyzing {window.process_name or 'the active window'}…</b>")
        self._status.setText("Reading the screen…")
        self._menu.hide()
        self._panel.hide()
        self._raise()

    def show_menu(self, ident: AppIdentification, element_count: int) -> None:
        self._app_name = ident.app_name
        version = f" · v{ident.detected_version_hint}" if ident.detected_version_hint else ""
        self._appline.setText(
            f"<span style='font-size:15px;font-weight:600'>{ident.app_name}</span><br>"
            f"<span style='color:#57606a'>{ident.current_context}{version}</span>"
        )
        self._status.setText("")
        self._menu.set_identification(ident)
        self._panel.hide()
        self._menu.show()
        self._raise()

    def _set_tutorial_header(self, goal: str) -> None:
        self._appline.setText(
            f"<span style='font-size:15px;font-weight:600'>{self._app_name}</span><br>"
            f"<span style='color:#57606a'>Tutorial: {goal}</span>"
        )

    def show_planning(self, goal: str) -> None:
        self._set_tutorial_header(goal)
        self._status.setText("Planning your steps…")
        self._menu.hide()
        self._panel.hide()

    # --- interactive steps (M5) ---------------------------------------------------------
    def begin_steps(self, goal: str, app_name: str) -> None:
        """Switch the card into step mode once a plan is ready."""
        if not self._app_name:
            self._app_name = app_name
        self._set_tutorial_header(goal)
        self._status.setText("")
        self._menu.hide()
        self._panel.show()
        self._raise()

    def show_step(self, step: TutorialStep, index: int, total: int) -> None:
        self._panel.show_step(step, index, total)
        self._panel.show()
        self._raise()

    def set_step_status(self, text: str) -> None:
        self._panel.set_status(text)

    def show_hint(self, text: str) -> None:
        self._panel.show_hint(text)

    def show_complete(self) -> None:
        self._panel.show_complete()
