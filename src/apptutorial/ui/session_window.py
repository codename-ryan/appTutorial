"""The main session window: capture -> identify -> tutorial menu -> plan.

Shows a thumbnail of the captured window, the identified app, the tutorial menu, and the
generated plan. In M5 the plan view becomes the interactive one-step-at-a-time panel with
screen verification. The screenshot is shown from memory, never saved.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from apptutorial.ui.menu import TutorialMenu

if TYPE_CHECKING:
    from apptutorial.ai.schemas import AppIdentification, TutorialPlan
    from apptutorial.capture.backend import Screenshot, WindowInfo

_THUMB_WIDTH = 360


class SessionWindow(QWidget):
    goal_chosen = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("appTutorial")
        self.resize(560, 740)
        root = QVBoxLayout(self)

        self._thumb = QLabel()
        self._thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._header = QLabel()
        self._header.setWordWrap(True)
        self._header.setTextFormat(Qt.TextFormat.RichText)
        self._status = QLabel()
        self._status.setStyleSheet("color: gray;")
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

        root.addWidget(self._thumb)
        root.addWidget(self._header)
        root.addWidget(self._status)
        root.addWidget(self._menu)
        root.addWidget(self._plan_scroll, 1)

        self._menu.hide()
        self._plan_scroll.hide()

    def _raise(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def _set_thumb(self, screenshot: Screenshot) -> None:
        pix = QPixmap()
        pix.loadFromData(screenshot.png_bytes, "PNG")
        if pix.width() > _THUMB_WIDTH:
            pix = pix.scaledToWidth(_THUMB_WIDTH, Qt.TransformationMode.SmoothTransformation)
        self._thumb.setPixmap(pix)

    def set_status(self, text: str) -> None:
        self._status.setText(text)

    def show_analyzing(self, window: WindowInfo, screenshot: Screenshot) -> None:
        self._set_thumb(screenshot)
        self._header.setText(
            f"<b>Analyzing {window.process_name or 'the active window'}…</b>"
        )
        self._status.setText("Reading the screen…")
        self._menu.hide()
        self._plan_scroll.hide()
        self._raise()

    def show_menu(self, ident: AppIdentification, element_count: int) -> None:
        version = f" · v{ident.detected_version_hint}" if ident.detected_version_hint else ""
        self._header.setText(
            f"<h3 style='margin:2px 0'>{ident.app_name}</h3>"
            f"<p style='margin:2px 0;color:#444'>{ident.current_context}{version}</p>"
            f"<p style='margin:2px 0;color:#888'>{element_count} UI elements detected</p>"
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
        parts = [f"<h3 style='margin:2px 0'>{plan.goal}</h3>"]
        for step in plan.steps:
            parts.append(
                f"<p style='margin:10px 0 2px'><b>{step.index + 1}. {step.instruction}</b></p>"
                f"<p style='margin:0 0 0 14px;color:#555'>target: {step.target.description}</p>"
                f"<p style='margin:0 0 0 14px;color:#2e7d32'>done when: {step.done_when}</p>"
            )
        if not plan.steps:
            parts.append("<p>(no steps returned)</p>")
        self._plan.setText("".join(parts))
        self._menu.hide()
        self._plan_scroll.show()
        self._raise()
