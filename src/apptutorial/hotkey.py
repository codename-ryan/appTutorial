"""Global hotkey via the Win32 RegisterHotKey API, delivered to Qt's event loop.

RegisterHotKey is the reliable, OS-level way to get a global hotkey on Windows: the system
routes the key to us and SUPPRESSES it from the foreground app (so the hotkey won't also
trigger, say, Excel's Find & Replace). WM_HOTKEY arrives on the main thread's message queue
and is caught by a Qt native event filter. This avoids the keyboard-hook / AltGr problems of
userspace listeners.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal

_WM_HOTKEY = 0x0312
_MOD_ALT = 0x0001
_MOD_CONTROL = 0x0002
_MOD_SHIFT = 0x0004
_MOD_WIN = 0x0008
_MOD_NOREPEAT = 0x4000

_MODIFIERS = {
    "ctrl": _MOD_CONTROL,
    "control": _MOD_CONTROL,
    "alt": _MOD_ALT,
    "shift": _MOD_SHIFT,
    "win": _MOD_WIN,
    "super": _MOD_WIN,
    "cmd": _MOD_WIN,
}

_NAMED_KEYS = {
    "space": 0x20,
    "enter": 0x0D,
    "return": 0x0D,
    "tab": 0x09,
    "esc": 0x1B,
    "escape": 0x1B,
    "ins": 0x2D,
    "insert": 0x2D,
    "del": 0x2E,
    "delete": 0x2E,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
}
_FUNCTION_KEYS = {f"f{i}": 0x70 + (i - 1) for i in range(1, 25)}  # F1..F24


def _key_to_vk(key: str) -> int:
    if key in _FUNCTION_KEYS:
        return _FUNCTION_KEYS[key]
    if key in _NAMED_KEYS:
        return _NAMED_KEYS[key]
    if len(key) == 1 and key.isalnum():
        return ord(key.upper())  # A-Z / 0-9 share their ASCII virtual-key codes
    raise ValueError(f"unsupported hotkey key: {key!r}")


def parse_hotkey(hotkey: str) -> tuple[int, int]:
    """Parse e.g. ``ctrl+alt+t`` into ``(modifiers, virtual_key)`` for RegisterHotKey.

    Raises ValueError if there is no non-modifier key, more than one, or an unknown token.
    """
    parts = [p.strip().lower() for p in hotkey.split("+") if p.strip()]
    modifiers = 0
    vk: int | None = None
    for part in parts:
        if part in _MODIFIERS:
            modifiers |= _MODIFIERS[part]
        elif vk is not None:
            raise ValueError(f"hotkey {hotkey!r} has more than one non-modifier key")
        else:
            vk = _key_to_vk(part)
    if vk is None:
        raise ValueError(f"hotkey {hotkey!r} needs a non-modifier key")
    return modifiers | _MOD_NOREPEAT, vk


class HotkeyManager(QObject, QAbstractNativeEventFilter):
    """Registers a global hotkey and emits ``triggered`` on the main thread when pressed."""

    triggered = Signal()
    _HOTKEY_ID = 1

    def __init__(self, hotkey: str, parent: QObject | None = None) -> None:
        QObject.__init__(self, parent)
        QAbstractNativeEventFilter.__init__(self)
        self._hotkey = hotkey
        try:
            self._modifiers, self._vk = parse_hotkey(hotkey)
            self._valid = True
        except ValueError:
            self._modifiers, self._vk, self._valid = 0, 0, False
        self._registered = False
        self._last_error = 0
        self._app = None

    @property
    def valid(self) -> bool:
        return self._valid

    @property
    def registered(self) -> bool:
        return self._registered

    @property
    def last_error(self) -> int:
        """Win32 error code from the last failed RegisterHotKey (1409 = already in use)."""
        return self._last_error

    def start(self) -> bool:
        """Register the hotkey. Returns False if invalid or already taken by another app."""
        if not self._valid:
            return False
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            return False
        app.installNativeEventFilter(self)
        self._app = app
        try:
            ok = bool(
                ctypes.windll.user32.RegisterHotKey(
                    None, self._HOTKEY_ID, self._modifiers, self._vk
                )
            )
            self._last_error = 0 if ok else ctypes.windll.kernel32.GetLastError()
        except (AttributeError, OSError):
            ok = False
        self._registered = ok
        if not ok:
            app.removeNativeEventFilter(self)
            self._app = None
        return ok

    def stop(self) -> None:
        if self._registered:
            try:
                ctypes.windll.user32.UnregisterHotKey(None, self._HOTKEY_ID)
            except (AttributeError, OSError):
                pass
            self._registered = False
        if self._app is not None:
            self._app.removeNativeEventFilter(self)
            self._app = None

    def nativeEventFilter(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == _WM_HOTKEY and msg.wParam == self._HOTKEY_ID:
                self.triggered.emit()
        return False, 0
