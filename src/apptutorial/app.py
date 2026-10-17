"""appTutorial entry point.

M0: launches a do-nothing system tray icon. Later milestones add the global hotkey,
capture pipeline, AI layer, and the guided step panel.
"""

from __future__ import annotations

import argparse
import sys

from apptutorial import __version__
from apptutorial.config import Config, load_config


def _build(config: Config):
    """Construct the QApplication and tray icon. Returns ``(app, tray)``."""
    from PySide6.QtWidgets import QApplication

    from apptutorial.ui.tray import build_tray

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("appTutorial")
    # Tray app: don't quit when a transient window closes.
    app.setQuitOnLastWindowClosed(False)
    tray = build_tray(app)
    return app, tray


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="apptutorial",
        description="AI-powered on-screen software tutor",
    )
    parser.add_argument(
        "--version", action="version", version=f"apptutorial {__version__}"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Initialize config + UI objects and exit without the event loop (for verification).",
    )
    args = parser.parse_args(argv)

    config = load_config()
    app, tray = _build(config)

    if args.check:
        print(f"apptutorial {__version__} - M0 OK: config loaded, tray built.")
        print(f"  api key present : {config.has_api_key}")
        print(f"  hotkey          : {config.hotkey}")
        print(f"  denylist entries: {len(config.denylist)}")
        return 0

    tray.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
