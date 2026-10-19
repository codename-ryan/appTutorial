"""Application configuration: AI backend, hotkey, denylist, model IDs, telemetry path.

Values come from the environment; a local ``.env`` file is loaded if present.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Open-weight models served over an OpenAI-compatible API. Default is a local Ollama server,
# which keeps screenshots on the machine. Point OPENWEIGHT_BASE_URL at any OpenAI-compatible
# endpoint (vLLM, llama.cpp, OpenRouter, Together, ...) to use a different backend.
DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_API_KEY = "ollama"  # placeholder; local backends ignore it

# Must be VISION models (the app sends screenshots). See AGENTS.md "Model usage rules".
IDENTIFY_MODEL = "qwen2.5vl"  # app ID, tutorial planning, answering questions
VERIFY_MODEL = "qwen2.5vl"  # fallback "did they do the step?" check (local UIA/COM runs first)

# Ctrl+Shift (not Ctrl+Alt): on many keyboard layouts Windows treats Ctrl+Alt as AltGr,
# so Ctrl+Alt hotkeys register but never fire. Ctrl+Shift is reliable.
DEFAULT_HOTKEY = "ctrl+shift+t"

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

    openweight_base_url: str = DEFAULT_BASE_URL
    openweight_api_key: str = DEFAULT_API_KEY
    hotkey: str = DEFAULT_HOTKEY
    denylist: tuple[str, ...] = DEFAULT_DENYLIST
    identify_model: str = IDENTIFY_MODEL
    verify_model: str = VERIFY_MODEL
    telemetry_path: Path = field(default_factory=lambda: Path("telemetry.jsonl"))

    @property
    def backend_configured(self) -> bool:
        return bool(self.openweight_base_url)


def _parse_denylist(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return DEFAULT_DENYLIST
    items = tuple(x.strip().lower() for x in raw.split(",") if x.strip())
    return items or DEFAULT_DENYLIST


def load_config() -> Config:
    """Load configuration from the environment (reads ``.env`` if present)."""
    load_dotenv()
    return Config(
        openweight_base_url=os.environ.get("OPENWEIGHT_BASE_URL", DEFAULT_BASE_URL),
        openweight_api_key=os.environ.get("OPENWEIGHT_API_KEY", DEFAULT_API_KEY),
        identify_model=os.environ.get("OPENWEIGHT_IDENTIFY_MODEL", IDENTIFY_MODEL),
        verify_model=os.environ.get("OPENWEIGHT_VERIFY_MODEL", VERIFY_MODEL),
        hotkey=os.environ.get("APPTUTORIAL_HOTKEY", DEFAULT_HOTKEY),
        denylist=_parse_denylist(os.environ.get("APPTUTORIAL_DENYLIST")),
        telemetry_path=Path(os.environ.get("APPTUTORIAL_TELEMETRY_PATH", "telemetry.jsonl")),
    )
