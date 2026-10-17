"""Capture backend interface, the Windows implementation, and a platform factory.

Windows is the only backend in v1 (see SPEC.md). Keeping capture behind this interface
lets a macOS backend be added later without touching the rest of the app. The concrete
Windows backend lazy-imports the platform helpers so this module stays import-safe
everywhere (the abstract types are used by tests and the factory).
"""

from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class WindowInfo:
    """Metadata about the active window."""

    hwnd: int  # OS window handle (0 on non-Windows stubs)
    title: str
    process_name: str  # e.g. "excel.exe" (lowercased)
    left: int
    top: int
    width: int
    height: int
    scale_factor: float  # per-monitor DPI scale (1.0 = 100%)


@dataclass(frozen=True)
class Screenshot:
    """An in-memory screenshot of the active window. Never written to disk."""

    png_bytes: bytes
    width: int
    height: int
    scale_factor: float


class CaptureBackend(ABC):
    """Platform-specific capture operations."""

    @abstractmethod
    def active_window(self) -> WindowInfo | None:
        """Return info about the focused window, or ``None`` if unavailable."""

    @abstractmethod
    def capture_window(self, window: WindowInfo) -> Screenshot:
        """Capture only the given window region, normalized for DPI scale."""


class WindowsCaptureBackend(CaptureBackend):
    """Windows capture via pywin32 + mss (see capture/window.py, capture/screenshot.py)."""

    def active_window(self) -> WindowInfo | None:
        from apptutorial.capture.window import get_active_window

        return get_active_window()

    def capture_window(self, window: WindowInfo) -> Screenshot:
        from apptutorial.capture.screenshot import capture_window as _capture

        return _capture(window)


def get_capture_backend() -> CaptureBackend:
    """Return the capture backend for the current platform."""
    if sys.platform == "win32":
        return WindowsCaptureBackend()
    raise NotImplementedError(f"No capture backend for platform {sys.platform!r}")
