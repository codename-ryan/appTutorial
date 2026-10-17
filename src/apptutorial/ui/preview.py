"""Transient capture-preview window (M1 verification aid).

Shows what the capture layer grabbed - window metadata plus the screenshot - so capture,
DPI scaling, the denylist, and the hotkey can be verified by eye. Later milestones replace
this with the tutorial menu and step panel. The screenshot is shown from memory and is
never saved to disk.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from apptutorial.capture.backend import Screenshot, WindowInfo

_MAX_PREVIEW_WIDTH = 900


class CapturePreview(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("appTutorial - capture preview (M1)")
        layout = QVBoxLayout(self)
        self._info = QLabel()
        self._info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._image = QLabel()
        self._image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._info)
        layout.addWidget(self._image, 1)

    def show_capture(self, window: WindowInfo, screenshot: Screenshot) -> None:
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
        self.resize(min(pix.width() + 40, 960), min(pix.height() + 160, 900))
        self.show()
        self.raise_()
        self.activateWindow()
