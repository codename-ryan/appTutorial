"""Step side panel: one step at a time (instruction + what "done" looks like).

Shows the current step with Back / Why? / Next controls, a hint area (filled by the
verifier), and a status line ("Watching your screen…" / "Checking…"). The orchestrator
drives it. See SPEC.md §3 and §9.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from apptutorial.ai.schemas import TutorialStep

_CHECK = chr(0x2713)  # ✓


class StepPanel(QWidget):
    next_clicked = Signal()
    back_clicked = Signal()

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._progress = QLabel()
        self._progress.setObjectName("progress")
        self._bar = QProgressBar()
        self._bar.setObjectName("progressBar")
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(6)
        self._instruction = QLabel()
        self._instruction.setObjectName("instruction")
        self._instruction.setWordWrap(True)
        self._done = QLabel()
        self._done.setObjectName("doneWhen")
        self._done.setWordWrap(True)
        self._why = QLabel()
        self._why.setObjectName("why")
        self._why.setWordWrap(True)
        self._why.hide()
        self._hint = QLabel()
        self._hint.setObjectName("hint")
        self._hint.setWordWrap(True)
        self._hint.hide()
        self._status = QLabel()
        self._status.setObjectName("stepStatus")

        for widget in (
            self._progress,
            self._bar,
            self._instruction,
            self._done,
            self._why,
            self._hint,
            self._status,
        ):
            layout.addWidget(widget)
        layout.addStretch(1)

        row = QHBoxLayout()
        self._back = QPushButton("Back")
        self._back.clicked.connect(lambda: self.back_clicked.emit())
        self._why_btn = QPushButton("Why?")
        self._why_btn.setCheckable(True)
        self._why_btn.toggled.connect(self._toggle_why)
        self._next = QPushButton("Next")
        self._next.setObjectName("nextBtn")
        self._next.clicked.connect(lambda: self.next_clicked.emit())
        for button in (self._back, self._why_btn, self._next):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        row.addWidget(self._back)
        row.addWidget(self._why_btn)
        row.addStretch(1)
        row.addWidget(self._next)
        layout.addLayout(row)

    def _toggle_why(self, checked: bool) -> None:
        self._why.setVisible(checked and bool(self._why.text()))

    @staticmethod
    def _repolish(widget) -> None:
        """Re-apply the stylesheet after a dynamic property changes (e.g. the done state)."""
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _set_next_green(self, on: bool) -> None:
        self._next.setProperty("done", on)
        self._status.setProperty("ok", on)
        self._repolish(self._next)
        self._repolish(self._status)

    def show_step(self, step: TutorialStep, index: int, total: int) -> None:
        self._progress.setText(f"Step {index + 1} of {total}")
        self._bar.setRange(0, total)
        self._bar.setValue(index + 1)
        self._bar.show()
        self._instruction.setText(step.instruction)
        self._done.setText(f"{_CHECK} Done when: {step.done_when}")
        self._why.setText(step.rationale)
        self._why.hide()
        self._why_btn.setChecked(False)
        self._hint.clear()
        self._hint.hide()
        self._status.setText("Watching your screen…")
        self._back.setEnabled(index > 0)
        self._why_btn.setEnabled(True)
        self._next.setEnabled(True)
        self._next.setText("Finish" if index >= total - 1 else "Next")
        self._set_next_green(False)  # back to the neutral style for a fresh step

    def set_status(self, text: str) -> None:
        self._status.setText(text)

    def show_hint(self, text: str) -> None:
        self._hint.setText(f"Hint: {text}")
        self._hint.setVisible(bool(text))

    def show_step_done(self, is_last: bool) -> None:
        """Step looks complete: turn the Next button green and wait for the user to confirm."""
        self._hint.clear()
        self._hint.hide()
        self._status.setText(f"{_CHECK} Looks done - click to continue.")
        self._next.setText(f"{_CHECK} Finish" if is_last else f"{_CHECK} Next step")
        self._next.setEnabled(True)
        self._set_next_green(True)

    def show_complete(self) -> None:
        self._progress.clear()
        self._bar.hide()
        self._instruction.setText(f"{_CHECK} Tutorial complete!")
        self._done.clear()
        self._why.hide()
        self._why_btn.setEnabled(False)
        self._hint.hide()
        self._status.setText("Nice work - pick another tutorial or press your hotkey.")
        self._back.setEnabled(False)
        self._next.setEnabled(True)
        self._next.setText("Back to tutorials")
        self._set_next_green(True)
