"""Windows active-window metadata: process name, bounds, per-monitor DPI scale.

Uses pywin32 + psutil, with ctypes for DPI. See SPEC.md §6.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

import psutil
import win32gui
import win32process

from apptutorial.capture.backend import WindowInfo


def ensure_dpi_awareness() -> None:
    """Make the process per-monitor DPI aware so bounds/screenshots use true pixels.

    Safe to call repeatedly and when a given API is unavailable. Qt6 also sets this when
    the QApplication is created; calling it first is a harmless no-op in that case.
    """
    # PER_MONITOR_AWARE_V2 = -4 (best; Windows 10 1703+)
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE
        return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass


def exclude_from_capture(hwnd: int) -> bool:
    """Hide our own window from screen capture so it never appears in screenshots.

    The tutor card is always-on-top and overlaps the app being taught; without this, every
    screenshot we take (identify/plan/verify) would have the card baked in, occluding part of
    the target window. WDA_EXCLUDEFROMCAPTURE (Windows 10 2004+) makes the window render
    normally to the user but vanish from BitBlt/DXGI capture - mss then sees the app behind it.
    Returns True on success.
    """
    wda_excludefromcapture = 0x00000011
    try:
        return bool(ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, wda_excludefromcapture))
    except (AttributeError, OSError):
        return False


def move_window_physical(hwnd: int, left: int, top: int, width: int, height: int) -> None:
    """Place a window at an exact physical-pixel rect, keeping it top-most, without activating.

    Bypasses Qt's logical-coordinate/DPI transform so the highlight overlay lands precisely on
    the physical bounds reported by UIA / Excel COM (which Qt's own positioning gets wrong under
    mixed-DPI / multi-monitor setups).
    """
    hwnd_topmost = -1
    swp_noactivate = 0x0010
    left, top, width, height = int(left), int(top), int(width), int(height)
    try:
        set_window_pos = ctypes.windll.user32.SetWindowPos
        set_window_pos.argtypes = [
            wintypes.HWND,
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint,
        ]
        set_window_pos.restype = wintypes.BOOL
        set_window_pos(hwnd, hwnd_topmost, left, top, width, height, swp_noactivate)
        # Self-correct: a DPI-virtualized / Qt-managed layered window can land shifted by a
        # constant offset. Measure where it actually went and nudge by the difference so the
        # frame sits exactly on the target (invisible on big elements, obvious on tiny cells).
        rect = wintypes.RECT()
        if ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            dx = left - rect.left
            dy = top - rect.top
            if dx or dy:
                set_window_pos(
                    hwnd, hwnd_topmost, left + dx, top + dy, width, height, swp_noactivate
                )
    except (AttributeError, OSError):
        pass


def _window_scale(hwnd: int) -> float:
    """Return the DPI scale factor for the monitor the window is on (1.0 = 100%)."""
    try:
        dpi = ctypes.windll.user32.GetDpiForWindow(hwnd)
    except (AttributeError, OSError):
        dpi = 0
    return (dpi / 96.0) if dpi else 1.0


def window_info_for_hwnd(hwnd: int) -> WindowInfo | None:
    """Build a WindowInfo for a specific window handle (re-reads current bounds)."""
    if not hwnd or not win32gui.IsWindow(hwnd):
        return None

    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    width, height = right - left, bottom - top
    if width <= 0 or height <= 0:
        return None

    title = win32gui.GetWindowText(hwnd)

    process_name = ""
    try:
        _thread_id, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid:
            process_name = psutil.Process(pid).name().lower()
    except (psutil.Error, OSError, ValueError):
        process_name = ""

    return WindowInfo(
        hwnd=hwnd,
        title=title,
        process_name=process_name,
        left=left,
        top=top,
        width=width,
        height=height,
        scale_factor=_window_scale(hwnd),
    )


def get_active_window() -> WindowInfo | None:
    """Return info about the focused window, or ``None`` if there isn't a usable one."""
    return window_info_for_hwnd(win32gui.GetForegroundWindow())
