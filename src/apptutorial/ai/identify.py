"""App identification (Claude Sonnet 5 -> AppIdentification).

Takes the active-window screenshot + process name and returns the app, category, on-screen
context, and suggested tutorials. UIA grounding is added in M3. See SPEC.md §8.
"""

from __future__ import annotations

import base64

from apptutorial.ai.client import AIClient
from apptutorial.ai.schemas import AppIdentification
from apptutorial.config import IDENTIFY_MODEL

_SYSTEM = """You are appTutorial's app identifier. You are shown a screenshot of the user's \
active window and its OS process name.

Identify the application and what the user appears to be doing RIGHT NOW, grounded ONLY in \
what is visible in the screenshot. Never assume menus, buttons, or features from other \
versions of the app - describe only what you can actually see.

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
    client: AIClient, png_bytes: bytes, process_name: str
) -> AppIdentification:
    image_b64 = base64.standard_b64encode(png_bytes).decode("ascii")
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": image_b64,
                    },
                },
                {
                    "type": "text",
                    "text": _USER_TEXT.format(process=process_name or "(unknown)"),
                },
            ],
        }
    ]
    return client.parse(
        model=IDENTIFY_MODEL,
        call_type="identify",
        system=_SYSTEM,
        messages=messages,
        output_model=AppIdentification,
        max_tokens=1024,
    )
