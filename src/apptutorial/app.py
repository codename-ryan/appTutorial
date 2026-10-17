"""appTutorial entry point and session orchestrator.

M2: hotkey -> capture the active window -> identify the app with Claude Sonnet 5 (in a
background thread) -> show the result + suggested tutorials. Includes the sensitive-app
denylist, tray capture indicator + pause, and local per-call telemetry. Later milestones add
the tutorial menu and the guided step panel.
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


class _IdentifySignals(QObject):
    done = Signal(object)  # AppIdentification
    failed = Signal(str)


class _IdentifyTask(QRunnable):
    """Runs the (blocking, network) identification off the UI thread."""

    def __init__(self, client: AIClient, png_bytes: bytes, process_name: str) -> None:
        super().__init__()
        self._client = client
        self._png = png_bytes
        self._process = process_name
        self.signals = _IdentifySignals()

    def run(self) -> None:
        try:
            result = identify_app(self._client, self._png, self._process)
        except Exception as exc:  # delivered to the UI thread as a failure message
            self.signals.failed.emit(str(exc))
        else:
            self.signals.done.emit(result)


class AppController(QObject):
    """Owns session state and wires tray, hotkey, capture, identification, and preview."""

    def __init__(self, config: Config, app, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self.app = app
        self.paused = False
        self._identify_task: _IdentifyTask | None = None

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

    def start(self) -> None:
        self.tray.show()
        if not self.hotkey.start():
            self.tray.notify(
                "appTutorial",
                f"Could not register hotkey {self.config.hotkey}. "
                "Use the tray menu to capture.",
            )

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

        if not self.ai.available:
            self.preview.set_status(
                "No API key - add ANTHROPIC_API_KEY to .env to enable app identification."
            )
            return

        self.preview.set_status("Identifying the app with Claude Sonnet 5...")
        task = _IdentifyTask(self.ai, screenshot.png_bytes, window.process_name)
        task.signals.done.connect(self._on_identified)
        task.signals.failed.connect(self._on_identify_failed)
        self._identify_task = task  # keep a reference while it runs
        QThreadPool.globalInstance().start(task)

    def _on_identified(self, ident) -> None:
        self._identify_task = None
        self.preview.show_identification(ident)

    def _on_identify_failed(self, message: str) -> None:
        self._identify_task = None
        self.preview.set_status(f"Identification failed: {message}")


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
    app = _make_app()
    controller = AppController(config, app)

    if args.check:
        print(f"apptutorial {__version__} - M2 OK: capture + identification wired.")
        print(f"  api key present : {config.has_api_key}")
        print(f"  ai available    : {controller.ai.available}")
        print(f"  identify model  : {config.identify_model}")
        print(f"  hotkey          : {config.hotkey}  (parsed ok: {controller.hotkey.valid})")
        print(f"  backend         : {type(controller.backend).__name__}")
        print(f"  telemetry       : {config.telemetry_path}")
        return 0

    controller.start()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
