"""Tutorial menu: suggested tutorials (from identification) + a "type your own goal" box.

Emits ``goal_chosen`` with a human-readable goal string (a suggested tutorial's title, or
whatever the user typed). Styling comes from the parent window's stylesheet. See SPEC.md §3.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from apptutorial.ai.schemas import AppIdentification


class TutorialMenu(QWidget):
    goal_chosen = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        prompt = QLabel("What would you like to learn?")
        prompt.setStyleSheet("font-weight: 600;")
        layout.addWidget(prompt)

        self._buttons = QVBoxLayout()
        self._buttons.setSpacing(6)
        layout.addLayout(self._buttons)

        row = QHBoxLayout()
        self._custom = QLineEdit()
        self._custom.setPlaceholderText("Or type your own goal…")
        self._custom.returnPressed.connect(self._emit_custom)
        start = QPushButton("Start")
        start.setCursor(Qt.CursorShape.PointingHandCursor)
        start.clicked.connect(self._emit_custom)
        row.addWidget(self._custom)
        row.addWidget(start)
        layout.addLayout(row)

    def set_identification(self, ident: AppIdentification) -> None:
        while self._buttons.count():
            item = self._buttons.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for tutorial in ident.suggested_tutorials:
            button = QPushButton(f"{tutorial.title}   ·  {tutorial.kind}")
            button.setObjectName("tutorialBtn")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(
                lambda _checked=False, title=tutorial.title: self.goal_chosen.emit(title)
            )
            self._buttons.addWidget(button)

    def _emit_custom(self) -> None:
        text = self._custom.text().strip()
        if text:
            self.goal_chosen.emit(text)
