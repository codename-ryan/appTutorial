"""appTutorial entry point and session orchestrator.

M4: hotkey -> capture -> read UI elements + identify the app -> show a tutorial menu
(suggested tutorials or a typed goal) -> plan the steps with Claude Sonnet 5. Includes the
sensitive-app denylist, tray capture indicator + pause, single-instance guard, and local
per-call telemetry. M5 turns the plan into an interactive, verified step-by-step panel.
"""

from __future__ import annotations

import argparse
import sys

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from apptutorial import __version__
from apptutorial.accessibility.uia import format_elements
from apptutorial.ai.client import AIClient
from apptutorial.ai.identify import identify_app
from apptutorial.ai.plan import plan_tutorial
from apptutorial.capture.backend import CaptureBackend, get_capture_backend
from apptutorial.config import Config, load_config
from apptutorial.hotkey import HotkeyManager
from apptutorial.privacy.denylist import is_denied
from apptutorial.telemetry.logger import TelemetryLogger
from apptutorial.ui.session_window import SessionWindow
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
        from apptutorial.accessibility.uia import summarize_active_window

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


class _PlanSignals(QObject):
    done = Signal(object)  # TutorialPlan
    failed = Signal(str)


class _PlanTask(QRunnable):
    """Generates the tutorial plan off the UI thread."""

    def __init__(self, ai: AIClient, png_bytes, goal, app_name, elements_text) -> None:
        super().__init__()
        self._ai = ai
        self._png = png_bytes
        self._goal = goal
        self._app_name = app_name
        self._elements_text = elements_text
        self.signals = _PlanSignals()

    def run(self) -> None:
        try:
            plan = plan_tutorial(
                self._ai, self._png, self._goal, self._app_name, self._elements_text
            )
        except Exception as exc:
            self.signals.failed.emit(str(exc))
        else:
            self.signals.done.emit(plan)


class AppController(QObject):
    """Owns session state and drives capture -> identify -> menu -> plan."""

    def __init__(self, config: Config, app, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self.app = app
        self.paused = False
        self._analyze_task: _AnalyzeTask | None = None
        self._plan_task: _PlanTask | None = None

        # Capture context, kept so planning can reuse the screenshot + elements.
        self._window_info = None
        self._screenshot = None
        self._elements = None
        self._ident = None

        self.telemetry = TelemetryLogger(config.telemetry_path)
        self.ai = AIClient(config.anthropic_api_key, self.telemetry)
        self.backend: CaptureBackend = get_capture_backend()
        self.tray = TrayIcon(app, config.hotkey)
        self.hotkey = HotkeyManager(config.hotkey)
        self.window = SessionWindow()

        self.tray.capture_requested.connect(self.trigger_capture)
        self.tray.pause_toggled.connect(self.set_paused)
        self.tray.quit_requested.connect(app.quit)
        self.hotkey.triggered.connect(self._on_hotkey)
        self.window.goal_chosen.connect(self._on_goal_chosen)
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

    def _on_hotkey(self) -> None:
        print(f"[hotkey] {self.config.hotkey} pressed -> capturing", flush=True)
        self.trigger_capture()

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

        self._window_info = window
        self._screenshot = screenshot
        self._elements = None
        self._ident = None

        self.window.show_analyzing(window, screenshot)
        task = _AnalyzeTask(self.ai, window, screenshot)
        task.signals.elements.connect(self._on_elements)
        task.signals.identified.connect(self._on_identified)
        task.signals.failed.connect(self._on_identify_failed)
        self._analyze_task = task
        QThreadPool.globalInstance().start(task)

    def _on_elements(self, elements) -> None:
        self._elements = elements
        if self.ai.available:
            self.window.set_status("Identifying the app with Claude Sonnet 5…")
        else:
            self._analyze_task = None
            self.window.set_status(
                "No API key - add ANTHROPIC_API_KEY to .env to enable tutorials."
            )

    def _on_identified(self, ident) -> None:
        self._analyze_task = None
        self._ident = ident
        self.window.show_menu(ident, len(self._elements) if self._elements else 0)

    def _on_identify_failed(self, message: str) -> None:
        self._analyze_task = None
        self.window.set_status(f"Identification failed: {message}")

    def _on_goal_chosen(self, goal: str) -> None:
        if self._screenshot is None:
            return
        if not self.ai.available:
            self.window.set_status("No API key - add ANTHROPIC_API_KEY to .env.")
            return
        self.window.show_planning(goal)
        app_name = (
            self._ident.app_name
            if self._ident is not None
            else (self._window_info.process_name if self._window_info else "the app")
        )
        elements_text = format_elements(self._elements) if self._elements else None
        task = _PlanTask(self.ai, self._screenshot.png_bytes, goal, app_name, elements_text)
        task.signals.done.connect(self._on_planned)
        task.signals.failed.connect(self._on_plan_failed)
        self._plan_task = task
        QThreadPool.globalInstance().start(task)

    def _on_planned(self, plan) -> None:
        self._plan_task = None
        self.window.show_plan(plan)

    def _on_plan_failed(self, message: str) -> None:
        self._plan_task = None
        self.window.set_status(f"Planning failed: {message}")


def _run_hotkey_test() -> int:
    """Register several candidate global hotkeys and print which ones actually fire.

    Diagnostic only. Registers via the same thread-message + native-filter path the real app
    uses, so a combo that fires here will fire in the app. Auto-exits after 30s.
    """
    import ctypes
    import signal
    from ctypes import wintypes

    from PySide6.QtCore import QAbstractNativeEventFilter, QTimer
    from PySide6.QtWidgets import QApplication

    wm_hotkey = 0x0312
    mod_alt, mod_control, mod_shift, mod_norepeat = 0x1, 0x2, 0x4, 0x4000
    candidates = [
        (1, "ctrl+alt+t", mod_control | mod_alt | mod_norepeat, ord("T")),
        (2, "ctrl+shift+t", mod_control | mod_shift | mod_norepeat, ord("T")),
        (3, "ctrl+alt+j", mod_control | mod_alt | mod_norepeat, ord("J")),
    ]

    app = QApplication.instance() or QApplication(sys.argv)

    registered: dict[int, tuple[str, bool, int]] = {}
    for hotkey_id, name, mods, vk in candidates:
        ok = bool(ctypes.windll.user32.RegisterHotKey(None, hotkey_id, mods, vk))
        err = 0 if ok else ctypes.windll.kernel32.GetLastError()
        registered[hotkey_id] = (name, ok, err)

    class _Filter(QAbstractNativeEventFilter):
        def nativeEventFilter(self, event_type, message):
            if event_type == b"windows_generic_MSG":
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == wm_hotkey:
                    name = registered.get(msg.wParam, ("?", False, 0))[0]
                    print(f"  >>> FIRED: {name}", flush=True)
            return False, 0

    filt = _Filter()
    app.installNativeEventFilter(filt)

    print("hotkey-test: registration results")
    for name, ok, err in registered.values():
        status = "registered" if ok else f"FAILED (error {err}; 1409 = already in use)"
        print(f"  {name:14} {status}")
    print("\nNow press each combo (try left Ctrl + left Alt). 'FIRED: <combo>' = it works.")
    print("Auto-exits in 30 seconds (or press Ctrl+C here).")
    sys.stdout.flush()

    signal.signal(signal.SIGINT, signal.SIG_DFL)
    QTimer.singleShot(30000, app.quit)
    result = app.exec()
    for hotkey_id in registered:
        ctypes.windll.user32.UnregisterHotKey(None, hotkey_id)
    return result


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
    parser.add_argument(
        "--hotkey-test",
        action="store_true",
        help="Register several candidate hotkeys and print which ones fire (for diagnosis).",
    )
    args = parser.parse_args(argv)

    if args.hotkey_test:
        return _run_hotkey_test()

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
        print(f"apptutorial {__version__} - M4 OK: capture + identify + menu + planning wired.")
        print(f"  api key present : {config.has_api_key}")
        print(f"  ai available    : {controller.ai.available}")
        print(f"  identify/plan   : {config.identify_model}")
        print(f"  verify          : {config.verify_model}")
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
        print("  Note: no API key loaded - add ANTHROPIC_API_KEY to .env for tutorials.")
    print("  Quit: tray menu -> Quit, or press Ctrl+C in this terminal.")
    sys.stdout.flush()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
