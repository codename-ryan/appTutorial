"""Application configuration: API key, hotkey, denylist, model IDs, telemetry path.

Values come from the environment; a local ``.env`` file is loaded if present.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Model IDs are a deliberate product choice — see CLAUDE.md "Model usage rules".
IDENTIFY_MODEL = "claude-sonnet-5"  # app ID, tutorial planning, answering questions
VERIFY_MODEL = "claude-haiku-4-5"  # fast "did they do the step?" check

DEFAULT_HOTKEY = "ctrl+alt+h"

# Sensitive apps where capture auto-disables (matched on lowercased process name).
DEFAULT_DENYLIST: tuple[str, ...] = (
    "1password.exe",
    "bitwarden.exe",
    "keepass.exe",
    "keepassxc.exe",
    "lastpass.exe",
    "dashlane.exe",
)


@dataclass
class Config:
    """Resolved runtime configuration."""

    anthropic_api_key: str | None
    hotkey: str = DEFAULT_HOTKEY
    denylist: tuple[str, ...] = DEFAULT_DENYLIST
    identify_model: str = IDENTIFY_MODEL
    verify_model: str = VERIFY_MODEL
    telemetry_path: Path = field(default_factory=lambda: Path("telemetry.jsonl"))

    @property
    def has_api_key(self) -> bool:
        return bool(self.anthropic_api_key)


def _parse_denylist(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return DEFAULT_DENYLIST
    items = tuple(x.strip().lower() for x in raw.split(",") if x.strip())
    return items or DEFAULT_DENYLIST


def load_config() -> Config:
    """Load configuration from the environment (reads ``.env`` if present)."""
    load_dotenv()
    return Config(
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
        hotkey=os.environ.get("APPTUTORIAL_HOTKEY", DEFAULT_HOTKEY),
        denylist=_parse_denylist(os.environ.get("APPTUTORIAL_DENYLIST")),
        telemetry_path=Path(os.environ.get("APPTUTORIAL_TELEMETRY_PATH", "telemetry.jsonl")),
    )
