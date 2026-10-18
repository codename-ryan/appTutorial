"""appTutorial entry point and session orchestrator.

Flow: hotkey -> capture the active window -> read UI elements + identify the app -> show a
tutorial menu (suggested tutorials or a typed goal) -> plan the steps with Claude Sonnet 5 ->
guide the user one step at a time, watching the screen locally and asking Claude Haiku to
verify each step before advancing. Includes the sensitive-app denylist, tray capture
indicator + pause, single-instance guard, and local per-call telemetry.
"""

from __future__ import annotations

import argparse
import sys

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal

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


class _WatchSignals(QObject):
    result = Signal(object)  # fingerprint (list[int]) or None


class _WatchTask(QRunnable):
    """Re-reads the target window and fingerprints it - off the UI thread, no AI call.

    Cheap perceptual hash used only to notice when the screen has changed and settled; the
    screenshot never leaves this worker.
    """

    def __init__(self, hwnd: int, rect: tuple[int, int, int, int] | None = None) -> None:
        super().__init__()
        self._hwnd = hwnd
        self._rect = rect  # focus the fingerprint on this target box, if known
        self.signals = _WatchSignals()

    def run(self) -> None:
        from apptutorial.capture.change_detector import fingerprint
        from apptutorial.capture.screenshot import capture_window, crop_png, image_box_from_rect
        from apptutorial.capture.window import window_info_for_hwnd

        try:
            window = window_info_for_hwnd(self._hwnd)
            if window is None:
                self.signals.result.emit(None)
                return
            shot = capture_window(window)
            png = shot.png_bytes
            if self._rect is not None:
                box = image_box_from_rect(window, shot.width, shot.height, self._rect)
                png = crop_png(shot.png_bytes, box) or shot.png_bytes
            self.signals.result.emit(fingerprint(png))
        except Exception:  # a transient capture hiccup shouldn't kill the watch loop
            self.signals.result.emit(None)


class _VerifySignals(QObject):
    done = Signal(object)  # StepVerification
    failed = Signal(str)


class _VerifyTask(QRunnable):
    """Captures a fresh screenshot of the target window and asks Haiku if the step is done."""

    def __init__(
        self, ai: AIClient, hwnd: int, step, app_name: str, rect: tuple | None = None
    ) -> None:
        super().__init__()
        self._ai = ai
        self._hwnd = hwnd
        self._step = step
        self._app_name = app_name
        self._rect = rect  # target box, for a focused close-up image
        self.signals = _VerifySignals()

    def run(self) -> None:
        from apptutorial.accessibility.uia import format_elements, summarize_active_window
        from apptutorial.ai.verify import verify_step
        from apptutorial.capture.screenshot import capture_window, crop_png, image_box_from_rect
        from apptutorial.capture.window import window_info_for_hwnd

        try:
            window = window_info_for_hwnd(self._hwnd)
            if window is None:
                self.signals.failed.emit("target window not found")
                return
            shot = capture_window(window)
            crop = None
            if self._rect is not None:
                box = image_box_from_rect(window, shot.width, shot.height, self._rect)
                crop = crop_png(shot.png_bytes, box)
            # Ground the check in the live accessibility tree (control states vision can miss).
            # Lighter limits than identification keeps this check responsive.
            try:
                elements = summarize_active_window(
                    self._hwnd, max_elements=60, max_depth=8, max_visit=450
                )
                elements_text = format_elements(elements) if elements else None
            except Exception:
                elements_text = None
            result = verify_step(
                self._ai, shot.png_bytes, self._step, self._app_name, elements_text, crop
            )
        except Exception as exc:
            self.signals.failed.emit(str(exc))
        else:
            self.signals.done.emit(result)


class _ResolveSignals(QObject):
    resolved = Signal(int, object)  # (step_index, rect-or-None)


class _ResolveTask(QRunnable):
    """Resolves a step's target element to a screen box via UIA, so tracking can focus on it."""

    def __init__(self, hwnd: int, step_index: int, name_hint: str, role_hint: str | None) -> None:
        super().__init__()
        self._hwnd = hwnd
        self._step_index = step_index
        self._name_hint = name_hint
        self._role_hint = role_hint
        self.signals = _ResolveSignals()

    def run(self) -> None:
        from apptutorial.accessibility.uia import find_element_rect

        try:
            rect = find_element_rect(self._hwnd, self._name_hint, self._role_hint)
        except Exception:
            rect = None
        self.signals.resolved.emit(self._step_index, rect)


class AppController(QObject):
    """Owns session state and drives capture -> identify -> menu -> plan -> guided steps."""

    _WATCH_INTERVAL_MS = 800  # how often the local screen fingerprint is taken
    # Verify at least this often (in watch ticks) even if no screen change is detected, so a
    # step still advances when the change is too subtle for the local fingerprint to catch.
    _PERIODIC_VERIFY_TICKS = 6  # ~5s at the watch interval

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

        # Interactive-step state (M5). The watch loop fingerprints the target window and only
        # calls Haiku to verify once the screen has changed and settled.
        self._plan = None
        self._steps: list = []
        self._step_index = 0
        self._guiding = False
        self._verifying = False
        self._verify_step_index = -1  # which step the in-flight verify is judging
        self._awaiting_next = False  # step detected done; waiting for the user to click Next
        self._completed = False  # whole tutorial finished; Next now returns to the menu
        self._watch_in_flight = False
        self._ticks_since_verify = 0  # safety net: verify periodically even without a change
        self._baseline_fp = None
        self._prev_fp = None
        self._target_rect = None  # screen box of the current step's target element (if resolved)
        self._watch_task: _WatchTask | None = None
        self._verify_task: _VerifyTask | None = None
        self._resolve_task: _ResolveTask | None = None
        self._watch_timer = QTimer(self)
        self._watch_timer.setInterval(self._WATCH_INTERVAL_MS)
        self._watch_timer.timeout.connect(self._tick)

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
        self.window.next_clicked.connect(self._on_next)
        self.window.back_clicked.connect(self._on_back)
        self.window.closed.connect(self._stop_guiding)  # closing the card ends the loop
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
        if paused:
            self._watch_timer.stop()
        elif self._guiding and not self._awaiting_next:
            # Resuming: re-baseline so a change made while paused doesn't false-trigger.
            self._baseline_fp = None
            self._prev_fp = None
            self.window.set_step_status("Watching your screen…")
            self._watch_timer.start()

    def trigger_capture(self) -> None:
        if self.paused:
            self.tray.notify("appTutorial", "Capture is paused.")
            return
        self._stop_guiding()  # a fresh capture ends any tutorial in progress
        self._completed = False
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
        self._plan = plan
        self._steps = list(plan.steps)
        app_name = plan.app_name or (self._ident.app_name if self._ident else "the app")
        self.window.begin_steps(plan.goal, app_name)
        if not self._steps:
            self.window.set_status("Claude didn't return any steps - try a different goal.")
            return
        self._start_step(0)

    def _on_plan_failed(self, message: str) -> None:
        self._plan_task = None
        self.window.set_status(f"Planning failed: {message}")

    # --- interactive step loop (M5) -----------------------------------------------------
    def _current_app_name(self) -> str:
        if self._plan is not None and self._plan.app_name:
            return self._plan.app_name
        if self._ident is not None:
            return self._ident.app_name
        return self._window_info.process_name if self._window_info else "the app"

    def _start_step(self, index: int) -> None:
        self._step_index = index
        step = self._steps[index]
        self.window.show_step(step, index, len(self._steps))
        # Re-baseline for the new step so its own screen state is the reference.
        self._baseline_fp = None
        self._prev_fp = None
        self._ticks_since_verify = 0
        self._awaiting_next = False
        self._completed = False
        self._target_rect = None
        self._guiding = True
        if self._window_info is not None:
            w = self._window_info
            print(
                f"[step {index + 1}/{len(self._steps)}] watching '{w.title}' "
                f"({w.process_name or '?'}, hwnd={w.hwnd}): {step.instruction}",
                flush=True,
            )
            self._resolve_target(index, step)
        if not self.paused:
            self._watch_timer.start()

    def _resolve_target(self, index: int, step) -> None:
        """Kick off a best-effort UIA lookup of the step's target box (focuses tracking on it)."""
        hint = step.target.uia_name_hint if step.target else None
        if not hint:
            return
        task = _ResolveTask(self._window_info.hwnd, index, hint, step.target.uia_role_hint)
        task.signals.resolved.connect(self._on_target_resolved)
        self._resolve_task = task
        QThreadPool.globalInstance().start(task)

    def _on_target_resolved(self, index: int, rect) -> None:
        self._resolve_task = None
        if not self._guiding or index != self._step_index or rect is None:
            return
        self._target_rect = rect
        print(f"[target] step {index + 1} box = {rect}", flush=True)
        # Detection now focuses on the box; re-baseline so the switch doesn't false-trigger.
        self._baseline_fp = None
        self._prev_fp = None

    def _stop_guiding(self) -> None:
        self._guiding = False
        self._awaiting_next = False
        self._watch_timer.stop()

    def _tick(self) -> None:
        if (
            not self._guiding
            or self.paused
            or self._verifying
            or self._awaiting_next
            or self._window_info is None
        ):
            return
        self._ticks_since_verify += 1
        if self._ticks_since_verify >= self._PERIODIC_VERIFY_TICKS:
            print("[watch] periodic check", flush=True)
            self._trigger_verify()
            return
        if self._watch_in_flight:
            return
        self._watch_in_flight = True
        task = _WatchTask(self._window_info.hwnd, self._target_rect)
        task.signals.result.connect(self._on_watch)
        self._watch_task = task
        QThreadPool.globalInstance().start(task)

    def _on_watch(self, fingerprint) -> None:
        self._watch_in_flight = False
        self._watch_task = None
        if (
            not self._guiding
            or self.paused
            or self._verifying
            or self._awaiting_next
            or fingerprint is None
        ):
            return

        from apptutorial.capture.change_detector import changed, difference, settled

        if self._baseline_fp is None:
            self._baseline_fp = fingerprint
            self._prev_fp = fingerprint
            return

        if changed(self._baseline_fp, fingerprint) and settled(self._prev_fp, fingerprint):
            print(
                f"[watch] screen changed ({difference(self._baseline_fp, fingerprint)} bits)"
                " -> checking",
                flush=True,
            )
            # Reset the baseline so we don't re-verify the same change until it moves again.
            self._baseline_fp = fingerprint
            self._prev_fp = fingerprint
            self._trigger_verify()
            return
        self._prev_fp = fingerprint

    def _trigger_verify(self) -> None:
        if self._verifying or self._window_info is None or not self.ai.available:
            return
        self._verifying = True
        self._verify_step_index = self._step_index
        self._ticks_since_verify = 0
        self.window.set_step_status("Checking…")
        step = self._steps[self._step_index]
        task = _VerifyTask(
            self.ai, self._window_info.hwnd, step, self._current_app_name(), self._target_rect
        )
        task.signals.done.connect(self._on_verify)
        task.signals.failed.connect(self._on_verify_failed)
        self._verify_task = task
        QThreadPool.globalInstance().start(task)

    def _on_verify(self, result) -> None:
        self._verifying = False
        self._verify_task = None
        print(
            f"[verify] step {self._verify_step_index + 1}: {result.status} "
            f"(conf {result.confidence:.2f}) - {result.observation}",
            flush=True,
        )
        # Ignore a result that arrives after the user manually moved to another step.
        if not self._guiding or self._awaiting_next or self._verify_step_index != self._step_index:
            return
        if result.status == "done" and result.confidence >= 0.5:
            self._mark_step_done()
            return
        if result.status in ("not_done", "off_track") and result.hint:
            self.window.show_hint(result.hint)
        self.window.set_step_status("Watching your screen…")

    def _mark_step_done(self) -> None:
        """Step looks complete: stop watching and let the user confirm with the green button."""
        self._awaiting_next = True
        self._watch_timer.stop()
        is_last = self._step_index + 1 >= len(self._steps)
        self.window.show_step_done(is_last)

    def _on_verify_failed(self, message: str) -> None:
        self._verifying = False
        self._verify_task = None
        print(f"[verify] failed: {message}", flush=True)
        if self._guiding:
            self.window.set_step_status("Watching your screen… (last check failed)")

    def _advance(self) -> None:
        if self._step_index + 1 < len(self._steps):
            self._start_step(self._step_index + 1)
        else:
            self._complete()

    def _complete(self) -> None:
        self._stop_guiding()
        self._completed = True  # Next now returns to the tutorial menu
        self.window.show_complete()

    def _restart_to_menu(self) -> None:
        """From the completion screen, go back to the tutorial options for the same app."""
        self._completed = False
        self._guiding = False
        self._awaiting_next = False
        if self._ident is not None:
            self.window.show_menu(self._ident, len(self._elements) if self._elements else 0)
        else:
            self.trigger_capture()  # no cached identification: just re-capture

    def _on_next(self) -> None:
        if self._completed:
            self._restart_to_menu()
            return
        if not self._guiding:
            return
        self._advance()

    def _on_back(self) -> None:
        if self._guiding and self._step_index > 0:
            self._start_step(self._step_index - 1)


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
    parser.add_argument("--version", action="version", version=f"apptutorial {__version__}")
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
        print(f"apptutorial {__version__} - M5 OK: capture + identify + menu + plan + verify.")
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
