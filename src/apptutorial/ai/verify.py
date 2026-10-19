"""Step verification (open-weight vision model -> StepVerification).

The fallback "did they do the step?" check, run when the deterministic local check can't decide
and the screen changes (or on a periodic heartbeat). Judges the current step from a fresh
screenshot plus the live accessibility (UIA) element list, which is reliable ground truth for
control states that are easy to miss in a screenshot. See SPEC.md §8.
"""

from __future__ import annotations

from apptutorial.ai.client import AIClient, image_content_block
from apptutorial.ai.schemas import StepVerification, TutorialStep
from apptutorial.config import VERIFY_MODEL

_SYSTEM = """You verify whether ONE tutorial step has been completed. You are given the step's \
instruction, what 'done' looks like, a screenshot of the user's app, and (when available) a list \
of the live on-screen UI elements from the accessibility tree.

Use BOTH sources. The UI element list is reliable ground truth for which controls exist and \
their state (a selected tab, an open dialog/window, a checked box, a focused field); the \
screenshot shows layout and content. If either one clearly shows the done condition is met, \
treat the step as done.

Choose status:
- "done": the done condition is satisfied - visible in the screenshot OR reflected in the UI \
elements.
- "not_done": the done condition is not met yet.
- "off_track": the user navigated somewhere that leads away from the step.
- "unclear": you genuinely cannot tell from either source.

Judge the END STATE, not how they got there: a step completed via a keyboard shortcut, the \
ribbon, or a right-click menu still counts as done. Don't demand a pixel-perfect match - accept \
reasonable equivalents. When not done or off track, give one short, specific hint naming the next \
concrete action. Keep observation to one sentence naming the concrete evidence you used."""


def verify_step(
    client: AIClient,
    png_bytes: bytes,
    step: TutorialStep,
    app_name: str,
    elements_text: str | None = None,
    crop_png_bytes: bytes | None = None,
    model: str = VERIFY_MODEL,
) -> StepVerification:
    signals = ", ".join(step.done_signals) or "(none)"
    content: list[dict] = [image_content_block(png_bytes)]
    if crop_png_bytes:
        caption = f"Close-up of the target ({step.target.description}):"
        content.append({"type": "text", "text": caption})
        content.append(image_content_block(crop_png_bytes))
    text = (
        f"App: {app_name}\n"
        f"Step instruction: {step.instruction}\n"
        f"Done when: {step.done_when}\n"
        f"Done signals: {signals}\n"
    )
    if elements_text:
        text += (
            "\nLive UI elements currently on screen (accessibility tree - use as ground truth "
            "for element names and states):\n"
            f"{elements_text}\n"
        )
    text += "\nHas this step been completed? Judge from the screenshot and the UI elements."
    content.append({"type": "text", "text": text})
    messages = [{"role": "user", "content": content}]
    return client.parse(
        model=model,
        call_type="verify",
        system=_SYSTEM,
        messages=messages,
        output_model=StepVerification,
        max_tokens=512,
        step_index=step.index,
    )
