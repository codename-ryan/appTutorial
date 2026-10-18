"""Step verification (Claude Haiku 4.5 -> StepVerification).

The fast "did they do the step?" check, run when the screen changes. Judges the current
step purely from a fresh screenshot. See SPEC.md §8.
"""

from __future__ import annotations

import base64

from apptutorial.ai.client import AIClient
from apptutorial.ai.schemas import StepVerification, TutorialStep
from apptutorial.config import VERIFY_MODEL

_SYSTEM = """You verify whether a single tutorial step has been completed, judging ONLY from a \
screenshot of the user's app. You are given the step's instruction and what 'done' looks like.

Choose status:
- "done": the done condition is clearly visible in the screenshot.
- "not_done": the screen does not yet show the done condition.
- "off_track": the user did something that leads away from the step.
- "unclear": you cannot tell from the screenshot.

Be strict - only "done" when the done condition is actually visible. When not done or off \
track, give a short one-sentence hint nudging the user toward completing the step. Keep \
observation to one sentence about the relevant screen state."""


def verify_step(
    client: AIClient, png_bytes: bytes, step: TutorialStep, app_name: str
) -> StepVerification:
    image_b64 = base64.standard_b64encode(png_bytes).decode("ascii")
    signals = ", ".join(step.done_signals) or "(none)"
    text = (
        f"App: {app_name}\n"
        f"Step instruction: {step.instruction}\n"
        f"Done when: {step.done_when}\n"
        f"Done signals: {signals}\n\n"
        "Has this step been completed? Judge only from the screenshot."
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
        model=VERIFY_MODEL,
        call_type="verify",
        system=_SYSTEM,
        messages=messages,
        output_model=StepVerification,
        max_tokens=512,
        step_index=step.index,
    )
