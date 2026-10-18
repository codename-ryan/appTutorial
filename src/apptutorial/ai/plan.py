"""Tutorial planning (Claude Sonnet 5 -> TutorialPlan).

Turns a chosen tutorial or a typed goal into ordered, structured steps grounded in the
current screenshot + accessibility elements. See SPEC.md §8.
"""

from __future__ import annotations

import base64

from apptutorial.ai.client import AIClient
from apptutorial.ai.schemas import TutorialPlan
from apptutorial.config import IDENTIFY_MODEL

_SYSTEM = """You are appTutorial's tutorial planner for the app the user is using. You are \
given a screenshot of their current screen, the app name, their goal, and a list of real UI \
elements read from the window's accessibility tree.

Produce a concise, ordered, step-by-step plan to achieve the goal, grounded ONLY in what is \
actually visible in the screenshot and the UI element list. Do not invent menus, tabs, or \
buttons that aren't present, and never describe a different version's UI. Prefer the exact \
element names from the accessibility list.

Each step is a single atomic action (one click/type/choice) with:
- instruction: what to do, in plain language
- rationale: one sentence on why this step matters
- target: the element to act on - a short description, plus uia_name_hint (the exact \
accessibility label) and uia_role_hint (e.g. Button, TabItem) when available, else null
- done_when: a short observable condition meaning the step is complete
- done_signals: a few things visible on screen once the step is done

Keep the plan focused (usually 3-10 steps). Number steps starting at 0. If the goal can't be \
done from what's visible, return the best next steps to get there."""


def plan_tutorial(
    client: AIClient,
    png_bytes: bytes,
    goal: str,
    app_name: str,
    elements_text: str | None = None,
) -> TutorialPlan:
    image_b64 = base64.standard_b64encode(png_bytes).decode("ascii")
    text = (
        f"Application: {app_name}\n"
        f"The user's goal: {goal}\n\n"
        "Create the step-by-step plan, grounded only in what is visible."
    )
    if elements_text:
        text += (
            "\n\nUI elements detected via accessibility (authoritative labels - "
            "prefer these exact names):\n" + elements_text
        )
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
                {"type": "text", "text": text},
            ],
        }
    ]
    return client.parse(
        model=IDENTIFY_MODEL,
        call_type="plan",
        system=_SYSTEM,
        messages=messages,
        output_model=TutorialPlan,
        max_tokens=4096,
    )
