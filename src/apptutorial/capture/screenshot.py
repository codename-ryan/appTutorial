"""Active-window screenshot capture via mss.

Captures only the given window region in physical pixels (the process is per-monitor DPI
aware, so the region lines up 1:1). The screenshot is held in memory as PNG bytes and is
never written to disk. See SPEC.md §6 and §10.
"""

from __future__ import annotations

import io

import mss
from PIL import Image

from apptutorial.capture.backend import Screenshot, WindowInfo


def capture_window(window: WindowInfo) -> Screenshot:
    """Grab only the window's region and return it as in-memory PNG bytes."""
    region = {
        "left": window.left,
        "top": window.top,
        "width": window.width,
        "height": window.height,
    }
    with mss.mss() as sct:
        raw = sct.grab(region)

    image = Image.frombytes("RGB", raw.size, raw.rgb)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    return Screenshot(
        png_bytes=buffer.getvalue(),
        width=raw.width,
        height=raw.height,
        scale_factor=window.scale_factor,
    )
