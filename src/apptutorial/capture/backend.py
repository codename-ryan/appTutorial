"""Capture backend interface.

Windows is the only backend in v1 (see SPEC.md). Keeping capture behind this interface
lets a macOS backend be added later without touching the rest of the app.
"""

from __future__ import annotations

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
