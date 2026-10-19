"""appTutorial entry point and session orchestrator.

Flow: hotkey -> capture the active window -> read UI elements + identify the app -> show a
tutorial menu (suggested tutorials or a typed goal) -> plan the steps with an open-weight vision
model -> guide the user one step at a time. Each step is verified with a hybrid check: a
deterministic local check (UIA / Excel COM) when the step's completion is a well-defined state (a
tab selected, a dialog open, a cell selected), falling back to the vision model for visual steps.
Includes the sensitive-app denylist, tray capture indicator + pause, single-instance guard, and
local per-call telemetry.
"""

from __future__ import annotations

import argparse
import os
import re
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
from apptutorial.ui.overlay import HighlightOverlay
from apptutorial.ui.session_window import SessionWindow
from apptutorial.ui.tray import TrayIcon

# Step-loop diagnostics go to the terminal only when APPTUTORIAL_DEBUG is set, so normal runs
# stay quiet. Set APPTUTORIAL_DEBUG=1 to trace watching/verification.
_DEBUG = bool(os.environ.get("APPTUTORIAL_DEBUG"))


def _log(message: str) -> None:
    if _DEBUG:
        print(message, flush=True)


# A1-style cell or range reference, e.g. "B5" or "A1:C10" (optional $ anchors).
_CELL_REF_RE = re.compile(r"^\$?[A-Za-z]{1,3}\$?[0-9]{1,7}(?::\$?[A-Za-z]{1,3}\$?[0-9]{1,7})?$")


def _looks_like_cell(value) -> bool:
    return bool(value) and bool(_CELL_REF_RE.match(value.strip()))


def _cell_ref_of_step(step) -> str | None:
    """Best-effort cell/range reference a step targets, regardless of how the planner tagged it.

    Checks the structured `check` fields, then a cell-like accessibility hint, then a "cell X"
    mention in the instruction. Returns None for non-cell steps (they use UIA element bounds).
    """
    check = getattr(step, "check", None)
    if check is not None:
        if check.kind == "cell_value" and _looks_like_cell(check.target):
            return check.target.strip()
        for value in (check.target, check.expected):
            if _looks_like_cell(value):
                return value.strip()
    target = getattr(step, "target", None)
    hint = getattr(target, "uia_name_hint", None) if target else None
    if _looks_like_cell(hint):
        return hint.strip()
    instruction = getattr(step, "instruction", "") or ""
    if "cell" in instruction.lower():
        for token in re.findall(r"\$?[A-Za-z]{1,3}\$?[0-9]{1,7}", instruction):
            if _looks_like_cell(token):
                return token.replace("$", "")
    return None


class _AnalyzeSignals(QObject):
    elements = Signal(object)  # list[UIElement]
    identified = Signal(object)  # AppIdentification
    failed = Signal(str)


class _AnalyzeTask(QRunnable):
    """Reads the window's accessibility elements, then identifies the app - off the UI thread."""

    def __init__(self, ai: AIClient, window, screenshot, model: str) -> None:
        super().__init__()
        self._ai = ai
        self._window = window
        self._screenshot = screenshot
        self._model = model
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
                model=self._model,
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

    def __init__(self, ai: AIClient, png_bytes, goal, app_name, elements_text, model: str) -> None:
        super().__init__()
        self._ai = ai
        self._png = png_bytes
        self._goal = goal
        self._app_name = app_name
        self._elements_text = elements_text
        self._model = model
        self.signals = _PlanSignals()

    def run(self) -> None:
        try:
            plan = plan_tutorial(
                self._ai,
                self._png,
                self._goal,
                self._app_name,
                self._elements_text,
                model=self._model,
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
    """Captures a fresh screenshot of the target window and asks the vision model if done."""

    def __init__(
        self,
        ai: AIClient,
        hwnd: int,
        step,
        app_name: str,
        rect: tuple | None = None,
        model: str = "",
    ) -> None:
        super().__init__()
        self._ai = ai
        self._hwnd = hwnd
        self._step = step
        self._app_name = app_name
        self._rect = rect  # target box, for a focused close-up image
        self._model = model
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
                self._ai,
                shot.png_bytes,
                self._step,
                self._app_name,
                elements_text,
                crop,
                model=self._model,
            )
        except Exception as exc:
            self.signals.failed.emit(str(exc))
        else:
            self.signals.done.emit(result)


class _ResolveSignals(QObject):
    resolved = Signal(int, object)  # (step_index, list-of-boxes)


class _ResolveTask(QRunnable):
    """Resolves a step's target to highlight boxes - a cell's row+column headers (UIA GridPattern)
    or a single control (UIA element bounds). Both come from the captured window, like the ribbon
    highlight that already lines up.
    """

    def __init__(self, hwnd: int, step_index: int, step) -> None:
        super().__init__()
        self._hwnd = hwnd
        self._step_index = step_index
        self._step = step
        self.signals = _ResolveSignals()

    def run(self) -> None:
        boxes: list = []
        try:
            ref = _cell_ref_of_step(self._step)
            if ref:
                from apptutorial.accessibility.uia import find_cell_header_rects

                col_rect, row_rect = find_cell_header_rects(self._hwnd, ref)
                boxes = [col_rect, row_rect]
            else:
                target = self._step.target
                hint = target.uia_name_hint if target else None
                if hint:
                    from apptutorial.accessibility.uia import find_element_rect

                    boxes = [find_element_rect(self._hwnd, hint, target.uia_role_hint)]
        except Exception:
            boxes = []
        self.signals.resolved.emit(self._step_index, boxes)


class _CellRectTask(QRunnable):
    """Re-reads a cell's header boxes (UIA GridPattern) so the highlight tracks scrolling."""

    def __init__(self, hwnd: int, step_index: int, ref: str) -> None:
        super().__init__()
        self._hwnd = hwnd
        self._step_index = step_index
        self._ref = ref
        self.signals = _ResolveSignals()

    def run(self) -> None:
        from apptutorial.accessibility.uia import find_cell_header_rects

        try:
            col_rect, row_rect = find_cell_header_rects(self._hwnd, self._ref)
        except Exception:
            col_rect, row_rect = None, None
        self.signals.resolved.emit(self._step_index, [col_rect, row_rect])


class _LocalCheckSignals(QObject):
    result = Signal(object)  # True (done) / False (not done) / None (undetermined -> use AI)


class _LocalCheckTask(QRunnable):
    """Evaluates a step's deterministic check against the live UIA tree - fast, no AI call."""

    def __init__(self, hwnd: int, kind: str, target, expected) -> None:
        super().__init__()
        self._hwnd = hwnd
        self._kind = kind
        self._target = target
        self._expected = expected
        self.signals = _LocalCheckSignals()

    def run(self) -> None:
        from apptutorial.accessibility.local_check import evaluate_check

        try:
            result = evaluate_check(self._hwnd, self._kind, self._target, self._expected)
        except Exception:
            result = None
        self.signals.result.emit(result)


class AppController(QObject):
    """Owns session state and drives capture -> identify -> menu -> plan -> guided steps."""

    _WATCH_INTERVAL_MS = 800  # how often the local screen fingerprint is taken
    # Local checks can be transiently undetermined (e.g. Excel COM rejects calls while a cell is
    # being edited). Only fall back to AI after this many undetermined ticks in a row.
    _LOCAL_NONE_LIMIT = 8  # ~6s at the watch interval
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
        # calls the vision model to verify once the screen has changed and settled.
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
        self._target_rect = None  # single box for AI crop/fingerprint focus (element steps)
        self._overlay_boxes: list = []  # boxes currently highlighted (1 control, or 2 headers)
        # Deterministic local-check path (hybrid verification): poll UIA state for checkable
        # steps; fall back to AI only when the local check can't determine the answer.
        self._ai_fallback = False
        self._local_none_count = 0
        self._local_in_flight = False
        self._local_for_index = -1  # which step the in-flight local check is judging
        self._overlay_in_flight = False
        self._watch_task: _WatchTask | None = None
        self._verify_task: _VerifyTask | None = None
        self._resolve_task: _ResolveTask | None = None
        self._local_task: _LocalCheckTask | None = None
        self._cell_rect_task: _CellRectTask | None = None
        self._watch_timer = QTimer(self)
        self._watch_timer.setInterval(self._WATCH_INTERVAL_MS)
        self._watch_timer.timeout.connect(self._tick)
        # Cell highlights must follow scrolling, so re-read the cell's screen box frequently.
        self._overlay_timer = QTimer(self)
        self._overlay_timer.setInterval(200)
        self._overlay_timer.timeout.connect(self._refresh_overlay)

        self.telemetry = TelemetryLogger(config.telemetry_path)
        self.ai = AIClient(config.openweight_base_url, config.openweight_api_key, self.telemetry)
        self.backend: CaptureBackend = get_capture_backend()
        self.tray = TrayIcon(app, config.hotkey)
        self.hotkey = HotkeyManager(config.hotkey)
        self.window = SessionWindow()
        # Two overlays: a cell step highlights its column header AND its row header.
        self.overlays = [HighlightOverlay(), HighlightOverlay()]

        self.tray.capture_requested.connect(self.trigger_capture)
        self.tray.pause_toggled.connect(self.set_paused)
        self.tray.quit_requested.connect(app.quit)
        self.hotkey.triggered.connect(self._on_hotkey)
        self.window.goal_chosen.connect(self._on_goal_chosen)
        self.window.next_clicked.connect(self._on_next)
        self.window.back_clicked.connect(self._on_back)
        self.window.closed.connect(self._stop_guiding)  # closing the card ends the loop
        app.aboutToQuit.connect(self.hotkey.stop)  # unregister the global hotkey on exit
        app.aboutToQuit.connect(self._hide_overlays)  # don't leave a stray highlight on exit

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
        _log(f"[hotkey] {self.config.hotkey} pressed -> capturing")
        self.trigger_capture()

    def set_paused(self, paused: bool) -> None:
        self.paused = paused
        self.tray.set_paused(paused)
        if paused:
            self._watch_timer.stop()
            self._overlay_timer.stop()
            self._hide_overlays()
        elif self._guiding and not self._awaiting_next:
            # Resuming: re-baseline so a change made while paused doesn't false-trigger.
            self._baseline_fp = None
            self._prev_fp = None
            self.window.set_step_status("Watching your screen…")
            self._show_overlay()
            self._watch_timer.start()
            if self._is_cell_step():
                self._overlay_timer.start()

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
        task = _AnalyzeTask(self.ai, window, screenshot, self.config.identify_model)
        task.signals.elements.connect(self._on_elements)
        task.signals.identified.connect(self._on_identified)
        task.signals.failed.connect(self._on_identify_failed)
        self._analyze_task = task
        QThreadPool.globalInstance().start(task)

    def _on_elements(self, elements) -> None:
        self._elements = elements
        if self.ai.available:
            self.window.set_status(f"Identifying the app with {self.config.identify_model}…")
        else:
            self._analyze_task = None
            self.window.set_status(
                "AI backend unavailable - is the model server running? "
                "Check OPENWEIGHT_BASE_URL in .env."
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
            self.window.set_status("AI backend unavailable - check OPENWEIGHT_BASE_URL in .env.")
            return
        self.window.show_planning(goal)
        app_name = (
            self._ident.app_name
            if self._ident is not None
            else (self._window_info.process_name if self._window_info else "the app")
        )
        elements_text = format_elements(self._elements) if self._elements else None
        task = _PlanTask(
            self.ai,
            self._screenshot.png_bytes,
            goal,
            app_name,
            elements_text,
            self.config.identify_model,
        )
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
            self.window.set_status("The model didn't return any steps - try a different goal.")
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
        self._hide_overlays()  # clear the previous step's highlight until the new one resolves
        # Re-baseline for the new step so its own screen state is the reference.
        self._baseline_fp = None
        self._prev_fp = None
        self._ticks_since_verify = 0
        self._awaiting_next = False
        self._completed = False
        self._target_rect = None
        self._ai_fallback = False
        self._local_none_count = 0
        self._local_in_flight = False
        self._guiding = True
        if self._window_info is not None:
            w = self._window_info
            check = getattr(step, "check", None)
            if check is None:
                check_desc = "visual"
            else:
                check_desc = check.kind
                if check.target:
                    check_desc += f":{check.target}"
                if check.expected:
                    check_desc += f"={check.expected}"
            _log(
                f"[step {index + 1}/{len(self._steps)}] watching '{w.title}' "
                f"({w.process_name or '?'}, hwnd={w.hwnd}) [check={check_desc}]: "
                f"{step.instruction}"
            )
            self._resolve_target(index, step)
        if not self.paused:
            self._watch_timer.start()
            # Cell targets scroll with the sheet, so keep re-reading their position.
            if self._is_cell_step():
                self._overlay_timer.start()
            else:
                self._overlay_timer.stop()

    def _resolve_target(self, index: int, step) -> None:
        """Resolve the step's target box (cell via COM or control via UIA) off the UI thread.

        Focuses change-tracking on the target and positions the highlight overlay.
        """
        task = _ResolveTask(self._window_info.hwnd, index, step)
        task.signals.resolved.connect(self._on_target_resolved)
        self._resolve_task = task
        QThreadPool.globalInstance().start(task)

    def _on_target_resolved(self, index: int, boxes) -> None:
        self._resolve_task = None
        if not self._guiding or index != self._step_index:
            return
        live = [b for b in (boxes or []) if b]
        self._overlay_boxes = live
        # A single control box doubles as the AI crop/fingerprint focus; header pairs don't.
        self._target_rect = live[0] if len(live) == 1 else None
        _log(f"[target] step {index + 1} boxes = {live}")
        if not live:
            self._hide_overlays()
            return
        self._baseline_fp = None
        self._prev_fp = None
        self._show_overlay()

    def _show_overlay(self) -> None:
        if self._guiding and not self._awaiting_next and not self.paused:
            self._show_overlay_boxes(self._overlay_boxes)

    def _show_overlay_boxes(self, boxes) -> None:
        for i, overlay in enumerate(self.overlays):
            if i < len(boxes) and boxes[i]:
                overlay.show_box(boxes[i])
            else:
                overlay.hide_box()

    def _hide_overlays(self) -> None:
        for overlay in self.overlays:
            overlay.hide_box()

    def _is_cell_step(self) -> bool:
        return bool(self._steps and _cell_ref_of_step(self._steps[self._step_index]))

    def _refresh_overlay(self) -> None:
        """Re-read the current cell's header boxes so the highlight tracks scrolling."""
        ref = _cell_ref_of_step(self._steps[self._step_index]) if self._steps else None
        if (
            not self._guiding
            or self.paused
            or self._awaiting_next
            or self._overlay_in_flight
            or self._window_info is None
            or not ref
        ):
            return
        self._overlay_in_flight = True
        task = _CellRectTask(self._window_info.hwnd, self._step_index, ref)
        task.signals.resolved.connect(self._on_overlay_rect)
        self._cell_rect_task = task
        QThreadPool.globalInstance().start(task)

    def _on_overlay_rect(self, index: int, boxes) -> None:
        self._overlay_in_flight = False
        self._cell_rect_task = None
        if not self._guiding or index != self._step_index or self._awaiting_next or self.paused:
            return
        live = [b for b in (boxes or []) if b]
        self._overlay_boxes = live
        self._show_overlay_boxes(live)  # shows live boxes, hides the rest (scrolled off)

    def _stop_guiding(self) -> None:
        self._guiding = False
        self._awaiting_next = False
        self._watch_timer.stop()
        self._overlay_timer.stop()
        self._hide_overlays()

    def _deterministic_check(self):
        """Return the current step's StepCheck if it can be verified locally, else None."""
        if not self._steps:
            return None
        check = getattr(self._steps[self._step_index], "check", None)
        if check is None or check.kind in (None, "", "visual"):
            return None
        return check

    def _tick(self) -> None:
        # Keeps running while awaiting confirmation too, so an undo reverts the "looks good".
        if not self._guiding or self.paused or self._verifying or self._window_info is None:
            return

        # Hybrid verification: for a checkable step, poll UIA state locally (fast, no AI).
        check = self._deterministic_check()
        if check is not None and not self._ai_fallback:
            if not self._local_in_flight:
                self._local_in_flight = True
                self._local_for_index = self._step_index
                task = _LocalCheckTask(
                    self._window_info.hwnd, check.kind, check.target, check.expected
                )
                task.signals.result.connect(self._on_local_check)
                self._local_task = task
                QThreadPool.globalInstance().start(task)
            return

        # AI path: fingerprint the screen and verify on a real change. The periodic heartbeat is
        # suppressed while awaiting confirmation (change-detection alone catches an undo).
        if not self._awaiting_next:
            self._ticks_since_verify += 1
            if self._ticks_since_verify >= self._PERIODIC_VERIFY_TICKS:
                _log("[watch] periodic check")
                self._trigger_verify()
                return
        if self._watch_in_flight:
            return
        self._watch_in_flight = True
        task = _WatchTask(self._window_info.hwnd, self._target_rect)
        task.signals.result.connect(self._on_watch)
        self._watch_task = task
        QThreadPool.globalInstance().start(task)

    def _on_local_check(self, result) -> None:
        self._local_in_flight = False
        self._local_task = None
        # Ignore a result that arrives after the user manually moved to another step.
        if not self._guiding or self.paused or self._local_for_index != self._step_index:
            return
        if result is True:
            if not self._awaiting_next:
                _log(f"[local] step {self._step_index + 1}: done")
                self._mark_step_done()
            return
        if result is None:
            # Undetermined (e.g. Excel busy mid-edit). Don't revert on this; only count toward
            # AI fallback while still actively watching.
            if not self._awaiting_next:
                self._local_none_count += 1
                if self._local_none_count >= self._LOCAL_NONE_LIMIT:
                    _log(f"[local] step {self._step_index + 1}: undetermined -> AI fallback")
                    self._ai_fallback = True
                    self._baseline_fp = None
                    self._prev_fp = None
                    self._ticks_since_verify = 0
            return
        # result is False: the step is not (or no longer) done.
        self._local_none_count = 0
        if self._awaiting_next:
            self._revert_step_done()  # the user undid it - go back to actively guiding
        else:
            self.window.set_step_status("Watching your screen…")

    def _on_watch(self, fingerprint) -> None:
        self._watch_in_flight = False
        self._watch_task = None
        if not self._guiding or self.paused or self._verifying or fingerprint is None:
            return

        from apptutorial.capture.change_detector import changed, difference, settled

        if self._baseline_fp is None:
            self._baseline_fp = fingerprint
            self._prev_fp = fingerprint
            return

        if changed(self._baseline_fp, fingerprint) and settled(self._prev_fp, fingerprint):
            _log(
                f"[watch] screen changed ({difference(self._baseline_fp, fingerprint)} bits)"
                " -> checking"
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
            self.ai,
            self._window_info.hwnd,
            step,
            self._current_app_name(),
            self._target_rect,
            self.config.verify_model,
        )
        task.signals.done.connect(self._on_verify)
        task.signals.failed.connect(self._on_verify_failed)
        self._verify_task = task
        QThreadPool.globalInstance().start(task)

    def _on_verify(self, result) -> None:
        self._verifying = False
        self._verify_task = None
        _log(
            f"[verify] step {self._verify_step_index + 1}: {result.status} "
            f"(conf {result.confidence:.2f}) - {result.observation}"
        )
        # Ignore a result that arrives after the user manually moved to another step.
        if not self._guiding or self._verify_step_index != self._step_index:
            return
        if result.status == "done" and result.confidence >= 0.5:
            if not self._awaiting_next:
                self._mark_step_done()
            return
        # Not done. If we were showing "looks good", the user undid it - revert.
        if self._awaiting_next:
            if result.status in ("not_done", "off_track"):
                self._revert_step_done()
            return
        if result.status in ("not_done", "off_track") and result.hint:
            self.window.show_hint(result.hint)
        self.window.set_step_status("Watching your screen…")

    def _mark_step_done(self) -> None:
        """Step looks complete: show the green confirm button, but keep monitoring so that
        undoing it (e.g. deselecting the cell) reverts back to actively guiding the step."""
        if self._awaiting_next:
            return
        self._awaiting_next = True
        self._overlay_timer.stop()
        self._hide_overlays()  # drop the highlight while it looks done
        self._ticks_since_verify = 0
        is_last = self._step_index + 1 >= len(self._steps)
        self.window.show_step_done(is_last)
        # The watch/local timer keeps running so an undo is noticed.

    def _revert_step_done(self) -> None:
        """The step no longer looks done (the user undid it) - return to actively guiding it."""
        if not self._awaiting_next:
            return
        self._awaiting_next = False
        _log(f"[revert] step {self._step_index + 1}: no longer done -> watching")
        step = self._steps[self._step_index]
        self.window.show_step(step, self._step_index, len(self._steps))
        self._target_rect = None
        self._hide_overlays()
        self._resolve_target(self._step_index, step)
        if not self.paused and self._is_cell_step():
            self._overlay_timer.start()

    def _on_verify_failed(self, message: str) -> None:
        self._verifying = False
        self._verify_task = None
        _log(f"[verify] failed: {message}")
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
        self._overlay_timer.stop()
        self._hide_overlays()
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
        print(
            f"apptutorial {__version__} - OK: capture + identify + menu + plan + "
            "hybrid verify (local/AI) + highlight overlay."
        )
        print(f"  ai backend url  : {config.openweight_base_url}")
        print(f"  ai available    : {controller.ai.available}")
        print(f"  identify/plan   : {config.identify_model}")
        print(f"  verify (fallbk) : {config.verify_model}")
        print(f"  hotkey          : {config.hotkey}  (parsed ok: {controller.hotkey.valid})")
        print(f"  capture backend : {type(controller.backend).__name__}")
        print(f"  telemetry       : {config.telemetry_path}")
        print(f"  debug logging   : {_DEBUG}")
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
        print("  Note: AI backend not configured - set OPENWEIGHT_BASE_URL in .env.")
    print("  Quit: tray menu -> Quit, or press Ctrl+C in this terminal.")
    sys.stdout.flush()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
