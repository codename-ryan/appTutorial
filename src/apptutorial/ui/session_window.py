"""The main session window: capture -> identify -> tutorial menu -> plan.

A compact, frameless, always-on-top card docked to the top-right corner. It floats above the
app you're working in (so it doesn't vanish when that app takes focus) and stays until you
close it with the X. Draggable by its header. The screenshot is never shown or saved here.
In M5 the plan view becomes the interactive one-step-at-a-time panel with screen verification.
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
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from apptutorial.ui.menu import TutorialMenu

if TYPE_CHECKING:
    from apptutorial.ai.schemas import AppIdentification, TutorialPlan
    from apptutorial.capture.backend import Screenshot, WindowInfo

_STYLE = """
QFrame#card { background: #ffffff; border-radius: 14px; }
QLabel { color: #1f2328; font-size: 13px; }
QLabel#title { color: #2e7d32; font-weight: 600; font-size: 14px; }
QLabel#status { color: #6a737d; }
QPushButton { background: #f3f4f6; border: 1px solid #e2e4e8; border-radius: 8px;
              padding: 7px 10px; color: #1f2328; }
QPushButton:hover { background: #e9ebef; }
QPushButton#tutorialBtn { text-align: left; }
QPushButton#close { background: transparent; border: none; color: #6a737d; font-size: 15px; }
QPushButton#close:hover { background: #eceef1; border-radius: 13px; color: #1f2328; }
QLineEdit { background: #ffffff; border: 1px solid #d0d7de; border-radius: 8px; padding: 6px 8px; }
QScrollArea { border: none; background: transparent; }
"""


class SessionWindow(QWidget):
    goal_chosen = Signal(str)
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
        self.resize(360, 540)
        self._placed = False
        self._drag_offset = None

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
        close_btn.clicked.connect(self.hide)
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

        self._plan = QLabel()
        self._plan.setWordWrap(True)
        self._plan.setTextFormat(Qt.TextFormat.RichText)
        self._plan.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._plan.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._plan_scroll = QScrollArea()
        self._plan_scroll.setWidgetResizable(True)
        self._plan_scroll.setWidget(self._plan)

        layout.addWidget(self._appline)
        layout.addWidget(self._status)
        layout.addWidget(self._menu)
        layout.addWidget(self._plan_scroll, 1)

        self.setStyleSheet(_STYLE)
        self._menu.hide()
        self._plan_scroll.hide()

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
        self._appline.setText(
            f"<b>Analyzing {window.process_name or 'the active window'}…</b>"
        )
        self._status.setText("Reading the screen…")
        self._menu.hide()
        self._plan_scroll.hide()
        self._raise()

    def show_menu(self, ident: AppIdentification, element_count: int) -> None:
        version = f" · v{ident.detected_version_hint}" if ident.detected_version_hint else ""
        self._appline.setText(
            f"<span style='font-size:15px;font-weight:600'>{ident.app_name}</span><br>"
            f"<span style='color:#57606a'>{ident.current_context}{version}</span>"
        )
        self._status.setText("")
        self._menu.set_identification(ident)
        self._plan_scroll.hide()
        self._menu.show()
        self._raise()

    def show_planning(self, goal: str) -> None:
        self._status.setText(f"Planning: {goal} …")
        self._menu.hide()
        self._plan_scroll.hide()

    def show_plan(self, plan: TutorialPlan) -> None:
        self._status.setText("")
        parts = [
            f"<div style='font-size:15px;font-weight:600;margin-bottom:4px'>{plan.goal}</div>"
        ]
        for step in plan.steps:
            parts.append(
                f"<div style='margin:10px 0 2px'><b>{step.index + 1}. {step.instruction}</b></div>"
            )
            parts.append(
                f"<div style='margin-left:12px;color:#57606a'>"
                f"target: {step.target.description}</div>"
            )
            parts.append(
                f"<div style='margin-left:12px;color:#2e7d32'>"
                f"done when: {step.done_when}</div>"
            )
        if not plan.steps:
            parts.append("<div>(no steps returned)</div>")
        self._plan.setText("".join(parts))
        self._menu.hide()
        self._plan_scroll.show()
        self._raise()
