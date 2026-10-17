"""Transient capture + identification window (M1/M2 verification aid).

Shows what the capture layer grabbed (window metadata + screenshot) and, once identified,
the app Claude recognized plus its suggested tutorials. Later milestones replace this with
the real tutorial menu and step panel. The screenshot is shown from memory, never saved.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from apptutorial.capture.backend import Screenshot, WindowInfo

if TYPE_CHECKING:
    from apptutorial.ai.schemas import AppIdentification

_MAX_PREVIEW_WIDTH = 900


class CapturePreview(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("appTutorial - capture preview")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)

        self._info = QLabel()
        self._info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._status = QLabel()
        self._status.setStyleSheet("color: gray;")
        self._ident = QLabel()
        self._ident.setWordWrap(True)
        self._ident.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._image = QLabel()
        self._image.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(self._info)
        layout.addWidget(self._status)
        layout.addWidget(self._ident)
        layout.addWidget(self._image, 1)

    def show_capture(self, window: WindowInfo, screenshot: Screenshot) -> None:
        self._status.setText("")
        self._ident.setText("")
        self._info.setText(
            f"<b>title:</b> {window.title or '(none)'}<br>"
            f"<b>process:</b> {window.process_name or '(unknown)'}<br>"
            f"<b>bounds:</b> ({window.left}, {window.top}) &nbsp; "
            f"{window.width}&times;{window.height} px<br>"
            f"<b>scale factor:</b> {window.scale_factor:.2f} "
            f"({int(round(window.scale_factor * 100))}%)<br>"
            f"<b>screenshot:</b> {screenshot.width}&times;{screenshot.height} px, "
            f"{len(screenshot.png_bytes) // 1024} KB PNG"
        )
        pix = QPixmap()
        pix.loadFromData(screenshot.png_bytes, "PNG")
        if pix.width() > _MAX_PREVIEW_WIDTH:
            pix = pix.scaledToWidth(
                _MAX_PREVIEW_WIDTH, Qt.TransformationMode.SmoothTransformation
            )
        self._image.setPixmap(pix)
        self.resize(min(pix.width() + 40, 960), min(pix.height() + 240, 900))
        self.show()
        self.raise_()
        self.activateWindow()

    def set_status(self, text: str) -> None:
        self._status.setText(text)

    def show_identification(self, ident: AppIdentification) -> None:
        self._status.setText("")
        tutorials = "".join(
            f"<li><b>{t.title}</b> <i>({t.kind})</i></li>"
            for t in ident.suggested_tutorials
        ) or "<li>(none suggested)</li>"
        capabilities = ", ".join(ident.visible_capabilities) or "(none listed)"
        version = (
            f" &middot; version hint: {ident.detected_version_hint}"
            if ident.detected_version_hint
            else ""
        )
        self._ident.setText(
            f"<h3 style='margin:4px 0'>{ident.app_name} "
            f"<span style='font-weight:normal;color:gray'>({ident.app_category}, "
            f"{int(round(ident.confidence * 100))}% conf{version})</span></h3>"
            f"<p style='margin:2px 0'>{ident.current_context}</p>"
            f"<p style='margin:2px 0'><b>Visible:</b> {capabilities}</p>"
            f"<p style='margin:6px 0 2px'><b>Suggested tutorials</b></p>"
            f"<ul style='margin:2px 0'>{tutorials}</ul>"
        )
