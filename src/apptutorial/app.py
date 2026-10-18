"""appTutorial entry point and session orchestrator.

M3: hotkey -> capture the active window -> read its UI Automation elements and identify the
app with Claude Sonnet 5 (both off the UI thread) -> show the elements + result. Includes the
sensitive-app denylist, tray capture indicator + pause, and local per-call telemetry. Later
milestones add the tutorial menu and the guided step panel.
"""

from __future__ import annotations

import argparse
import sys

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from apptutorial import __version__
from apptutorial.ai.client import AIClient
from apptutorial.ai.identify import identify_app
from apptutorial.capture.backend import CaptureBackend, get_capture_backend
from apptutorial.config import Config, load_config
from apptutorial.hotkey import HotkeyManager
from apptutorial.privacy.denylist import is_denied
from apptutorial.telemetry.logger import TelemetryLogger
from apptutorial.ui.preview import CapturePreview
from apptutorial.ui.tray import TrayIcon


class _AnalyzeSignals(QObject):
    elements = Signal(object)  # list[UIElement]
    identified = Signal(object)  # AppIdentification
    failed = Signal(str)


class _AnalyzeTask(QRunnable):
    """Reads the window's accessibility elements, then identifies the app - off the UI thread."""

    def __init__(self, ai: AIClient, window, screenshot) -> None:
        super().__init__()
        self._ai = ai
        self._window = window
        self._screenshot = screenshot
        self.signals = _AnalyzeSignals()

    def run(self) -> None:
        from apptutorial.accessibility.uia import format_elements, summarize_active_window

        elements = summarize_active_window(self._window.hwnd)
        self.signals.elements.emit(elements)

        if not self._ai.available:
            return
        try:
            ident = identify_app(
                self._ai,
                self._screenshot.png_bytes,
                self._window.process_name,
                format_elements(elements) if elements else None,
            )
        except Exception as exc:  # delivered to the UI thread as a failure message
            self.signals.failed.emit(str(exc))
        else:
            self.signals.identified.emit(ident)


class AppController(QObject):
    """Owns session state and wires tray, hotkey, capture, analysis, and preview."""

    def __init__(self, config: Config, app, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self.app = app
        self.paused = False
        self._task: _AnalyzeTask | None = None

        self.telemetry = TelemetryLogger(config.telemetry_path)
        self.ai = AIClient(config.anthropic_api_key, self.telemetry)
        self.backend: CaptureBackend = get_capture_backend()
        self.tray = TrayIcon(app, config.hotkey)
        self.hotkey = HotkeyManager(config.hotkey)
        self.preview = CapturePreview()

        self.tray.capture_requested.connect(self.trigger_capture)
        self.tray.pause_toggled.connect(self.set_paused)
        self.tray.quit_requested.connect(app.quit)
        self.hotkey.triggered.connect(self.trigger_capture)
        app.aboutToQuit.connect(self.hotkey.stop)  # unregister the global hotkey on exit

    def start(self) -> bool:
        """Show the tray and register the hotkey. Returns whether the hotkey registered."""
        self.tray.show()
        registered = self.hotkey.start()
        if registered:
            self.tray.notify(
                "appTutorial",
                f"Running. Press {self.config.hotkey} over any window, or use this menu.",
            )
        else:
            self.tray.notify(
                "appTutorial",
                f"Running, but hotkey {self.config.hotkey} is unavailable. "
                "Use 'Capture in 3s' in this menu, or change APPTUTORIAL_HOTKEY in .env.",
            )
        return registered

    def set_paused(self, paused: bool) -> None:
        self.paused = paused
        self.tray.set_paused(paused)

    def trigger_capture(self) -> None:
        if self.paused:
            self.tray.notify("appTutorial", "Capture is paused.")
            return
        window = self.backend.active_window()
        if window is None:
            self.tray.notify("appTutorial", "No active window detected.")
            return
        if is_denied(window.process_name, self.config.denylist):
            self.tray.notify(
                "appTutorial",
                f"Capture disabled for {window.process_name} (sensitive app).",
            )
            return
        try:
            screenshot = self.backend.capture_window(window)
        except Exception as exc:  # surface any capture failure to the user, don't crash
            self.tray.notify("appTutorial", f"Capture failed: {exc}")
            return

        self.preview.show_capture(window, screenshot)
        self.preview.set_status("Reading the screen...")
        task = _AnalyzeTask(self.ai, window, screenshot)
        task.signals.elements.connect(self._on_elements)
        task.signals.identified.connect(self._on_identified)
        task.signals.failed.connect(self._on_identify_failed)
        self._task = task  # keep a reference while it runs
        QThreadPool.globalInstance().start(task)

    def _on_elements(self, elements) -> None:
        self.preview.show_elements(elements)
        if self.ai.available:
            self.preview.set_status("Identifying the app with Claude Sonnet 5...")
        else:
            self._task = None
            self.preview.set_status(
                "No API key - add ANTHROPIC_API_KEY to .env to enable identification."
            )

    def _on_identified(self, ident) -> None:
        self._task = None
        self.preview.show_identification(ident)

    def _on_identify_failed(self, message: str) -> None:
        self._task = None
        self.preview.set_status(f"Identification failed: {message}")


def _acquire_single_instance_lock():
    """Create a named mutex; return its handle, or None if another instance already holds it.

    Prevents two copies fighting over the global hotkey. The OS releases the mutex when the
    owning process exits (even if force-killed), so there is no stale-lock problem.
    """
    import ctypes

    error_already_exists = 183
    handle = ctypes.windll.kernel32.CreateMutexW(None, False, "apptutorial-single-instance")
    if ctypes.windll.kernel32.GetLastError() == error_already_exists:
        return None
    return handle


def _make_app():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("appTutorial")
    app.setQuitOnLastWindowClosed(False)
    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="apptutorial", description="AI-powered on-screen software tutor"
    )
    parser.add_argument(
        "--version", action="version", version=f"apptutorial {__version__}"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Initialize everything and exit without the event loop (for verification).",
    )
    args = parser.parse_args(argv)

    from apptutorial.capture.window import ensure_dpi_awareness

    ensure_dpi_awareness()
    config = load_config()

    if not args.check:
        lock = _acquire_single_instance_lock()  # held for the process lifetime
        if lock is None:
            print(
                "appTutorial is already running - look for the green icon in the system "
                "tray.\nTo restart, quit the running one first (tray menu -> Quit)."
            )
            return 1

    app = _make_app()
    controller = AppController(config, app)

    if args.check:
        print(f"apptutorial {__version__} - M3 OK: capture + accessibility + identification wired.")
        print(f"  api key present : {config.has_api_key}")
        print(f"  ai available    : {controller.ai.available}")
        print(f"  identify model  : {config.identify_model}")
        print(f"  hotkey          : {config.hotkey}  (parsed ok: {controller.hotkey.valid})")
        print(f"  backend         : {type(controller.backend).__name__}")
        print(f"  telemetry       : {config.telemetry_path}")
        return 0

    import signal

    from PySide6.QtWidgets import QSystemTrayIcon

    # Let Ctrl+C in the launching terminal stop the app (Qt's loop otherwise swallows it).
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    registered = controller.start()
    print(f"apptutorial {__version__} is running.")
    print("  Look for the GREEN SQUARE icon in the system tray (near the clock; it may be")
    print("  hidden under the ^ 'show hidden icons' arrow). Right-click it for the menu.")
    if registered:
        print(f"  Hotkey: {config.hotkey}  - press it over any window to capture.")
    else:
        if controller.hotkey.last_error == 1409:
            hint = (
                "another copy of appTutorial is probably still running and holding it - "
                "quit that one, then relaunch"
            )
        else:
            hint = "another app is using this combo - pick a free one in .env"
        print(
            f"  Hotkey: {config.hotkey} could NOT be registered "
            f"(error {controller.hotkey.last_error}). {hint}."
        )
        print("    Meanwhile you can use the tray menu's 'Capture in 3s (for testing)'.")
    if not QSystemTrayIcon.isSystemTrayAvailable():
        print("  WARNING: no system tray detected - the menu/indicator may not appear.")
    if not controller.ai.available:
        print("  Note: no API key loaded - add ANTHROPIC_API_KEY to .env for identification.")
    print("  Quit: tray menu -> Quit, or press Ctrl+C in this terminal.")
    sys.stdout.flush()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
