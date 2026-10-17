"""Global hotkey registration, bridged to the Qt main thread via a signal.

pynput's listener runs on its own thread; the hotkey callback only emits a Qt signal,
which Qt delivers (queued) on the main thread where capture/UI work is safe.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

_MODIFIERS = {"ctrl", "alt", "shift", "cmd"}
_ALIASES = {"win": "cmd", "super": "cmd", "control": "ctrl"}


def to_pynput_hotkey(hotkey: str) -> str:
    """Convert e.g. ``ctrl+alt+h`` to pynput's ``<ctrl>+<alt>+h`` format."""
    parts = [p.strip().lower() for p in hotkey.split("+") if p.strip()]
    pieces = []
    for part in parts:
        key = _ALIASES.get(part, part)
        pieces.append(f"<{key}>" if key in _MODIFIERS else key)
    return "+".join(pieces)


class HotkeyManager(QObject):
    """Registers a global hotkey and emits ``triggered`` when it is pressed."""

    triggered = Signal()

    def __init__(self, hotkey: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._combo = to_pynput_hotkey(hotkey)
        self._listener = None

    @property
    def combo(self) -> str:
        return self._combo

    def start(self) -> bool:
        """Start listening. Returns False if the hotkey could not be registered."""
        from pynput import keyboard

        try:
            self._listener = keyboard.GlobalHotKeys({self._combo: self._on_activate})
            self._listener.start()
            return True
        except Exception:
            self._listener = None
            return False

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def _on_activate(self) -> None:
        # Runs on pynput's listener thread; emitting queues the slot to the main thread.
        self.triggered.emit()
