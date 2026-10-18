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

Produce an ordered, step-by-step plan, grounded ONLY in what is actually visible in the \
screenshot and the UI element list. Never invent menus, tabs, or buttons, and never describe a \
different version's UI. Prefer the exact element labels from the list.

Write every step as a DIRECT COMMAND to the user - never a description or explanation:
- instruction: ONE imperative sentence that is a PHYSICAL ACTION the user performs - click, \
type, select, press, drag, open, choose, scroll, or right-click. Exactly one action; name the \
precise element. NEVER an observation or orientation: do not begin with Look, Notice, Find, \
Locate, Observe, See, Check, Identify, or "Go to". If the user must navigate somewhere first, \
write the click that gets there.
    GOOD: "Click the Developer tab."   "Type =SUM(A1:A10) in cell A11 and press Enter."
    BAD:  "Look at the ribbon."   "Locate the Developer tab."   "Find the Bold button."   \
"The Developer tab contains macro tools."
- done_when: the OBSERVABLE change on screen after the action succeeds - something a bystander \
could confirm by looking at the screen. Describe the app's state, NEVER the user's action, \
perception, or understanding.
    GOOD: "The Record Macro dialog is open."   "The Formulas tab is selected."   "Cell A11 \
shows the total."
    BAD:  "The user locates the button."   "When the user points out the menu."   "The user \
understands SUM."
- rationale: one short sentence on why the step helps.
- target: the element to act on; set uia_name_hint to its exact accessibility label and \
uia_role_hint to its control type when they appear in the element list, else null.
- done_signals: 1-3 concrete things visible on screen once the step is done.

Keep steps atomic (one action each) and the plan focused (usually 3-10 steps). Number steps \
from 0. If the goal isn't reachable from what's visible, give the best next steps toward it."""


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
