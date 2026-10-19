"""App identification (open-weight vision model -> AppIdentification).

Takes the active-window screenshot + process name + (optionally) a UI Automation element
summary, and returns the app, category, on-screen context, and suggested tutorials.
See SPEC.md §8.
"""

from __future__ import annotations

from apptutorial.ai.client import AIClient, image_content_block
from apptutorial.ai.schemas import AppIdentification
from apptutorial.config import IDENTIFY_MODEL

_SYSTEM = """You are appTutorial's app identifier. You are shown a screenshot of the user's \
active window, its OS process name, and (when available) a list of real UI elements read from \
the window via Windows accessibility.

Identify the application and what the user appears to be doing RIGHT NOW, grounded ONLY in \
what is visible in the screenshot and the accessibility elements. Never assume menus, buttons, \
or features from other versions of the app - describe only what you can actually see. When the \
accessibility element list is provided, treat those names as authoritative labels.

Then propose 2-5 tutorials tailored to this app and what's on screen. Each tutorial needs a \
kebab-case id, a short title, and a kind:
- "tour": a basic overview of what the app is and how to use it
- "feature": how to use one specific capability (e.g. macros, formulas)
- "project": an end-to-end goal the user might want to accomplish

Keep current_context to one sentence. Only set detected_version_hint if a version number is \
actually visible on screen; otherwise leave it null."""

_USER_TEXT = (
    "Process name: {process}. Identify this application and suggest tutorials, "
    "grounded only in what is visible."
)


def identify_app(
    client: AIClient,
    png_bytes: bytes,
    process_name: str,
    elements_text: str | None = None,
    model: str = IDENTIFY_MODEL,
) -> AppIdentification:
    text = _USER_TEXT.format(process=process_name or "(unknown)")
    if elements_text:
        text += (
            "\n\nUI elements detected via accessibility (authoritative labels - "
            "prefer these exact names):\n" + elements_text
        )
    messages = [
        {
            "role": "user",
            "content": [image_content_block(png_bytes), {"type": "text", "text": text}],
        }
    ]
    return client.parse(
        model=model,
        call_type="identify",
        system=_SYSTEM,
        messages=messages,
        output_model=AppIdentification,
        max_tokens=1024,
    )
