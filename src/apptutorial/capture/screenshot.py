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


def image_box_from_rect(
    window: WindowInfo,
    img_w: int,
    img_h: int,
    rect: tuple[int, int, int, int],
    margin_frac: float = 0.18,
) -> tuple[int, int, int, int] | None:
    """Convert a target element's screen rect to an image-relative crop box (with a margin).

    ``rect`` is (left, top, width, height) in screen pixels; the returned box is
    (left, top, right, bottom) within the window screenshot, clamped to its bounds. Returns
    ``None`` if the target doesn't meaningfully overlap the window (e.g. scrolled off-screen).
    """
    rl, rt, rw, rh = rect
    if rw <= 0 or rh <= 0:
        return None
    x = rl - window.left
    y = rt - window.top
    mx = int(rw * margin_frac) + 8
    my = int(rh * margin_frac) + 8
    left = max(0, x - mx)
    top = max(0, y - my)
    right = min(img_w, x + rw + mx)
    bottom = min(img_h, y + rh + my)
    if right - left < 8 or bottom - top < 8:
        return None
    return (left, top, right, bottom)


def crop_png(png_bytes: bytes, box: tuple[int, int, int, int] | None) -> bytes | None:
    """Crop a PNG to ``box`` (left, top, right, bottom) and return PNG bytes, or None."""
    if box is None:
        return None
    try:
        image = Image.open(io.BytesIO(png_bytes)).crop(box)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()
    except Exception:
        return None
