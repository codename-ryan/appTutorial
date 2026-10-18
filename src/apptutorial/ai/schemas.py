"""Pydantic models for Claude structured outputs.

M2 defines the identification schema; TutorialPlan (M4) and StepVerification (M5) are added
in their milestones. See SPEC.md §8.1 for the full shapes.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SuggestedTutorial(BaseModel):
    id: str  # kebab-case identifier, e.g. "record-a-macro"
    title: str
    kind: Literal["tour", "feature", "project"]


class AppIdentification(BaseModel):
    app_name: str
    app_category: str
    confidence: float  # 0.0 - 1.0
    detected_version_hint: str | None = None  # only if a version is visibly shown
    current_context: str  # one sentence on what's on screen right now
    visible_capabilities: list[str] = Field(default_factory=list)
    suggested_tutorials: list[SuggestedTutorial] = Field(default_factory=list)


class Target(BaseModel):
    """The UI element a step acts on."""

    description: str = Field(
        description="The on-screen element to act on, e.g. 'the Formulas tab in the ribbon'."
    )
    uia_name_hint: str | None = Field(
        default=None,
        description=(
            "The element's exact accessibility label, copied verbatim from the provided UI "
            "element list when it appears there; otherwise null."
        ),
    )
    uia_role_hint: str | None = Field(
        default=None,
        description="The element's control type, e.g. 'Button' or 'TabItem'; otherwise null.",
    )


class StepCheck(BaseModel):
    """A machine-checkable completion condition, evaluated locally via UI Automation.

    Lets the fast step-check run without the AI for well-defined UI states; ``visual`` falls
    back to the vision model. Produced by the planner (which understands the step) so the tight
    verification loop can stay deterministic.
    """

    kind: Literal[
        "element_selected",
        "element_focused",
        "element_present",
        "cell_selected",
        "checkbox_checked",
        "value_equals",
        "visual",
    ] = Field(
        default="visual",
        description=(
            "How completion can be checked. 'cell_selected': a spreadsheet cell/range is "
            "selected (put the reference in 'expected', e.g. 'B5'). 'element_selected': a "
            "tab/item becomes selected (name in 'target'). 'element_present': a dialog/pane/"
            "window appears (its title in 'target'). 'element_focused': a field gains focus "
            "(name in 'target'). 'checkbox_checked': a checkbox/toggle turns on (name in "
            "'target'). 'value_equals': a control shows a value (name in 'target', value in "
            "'expected'). 'visual': anything else - judged from the screenshot."
        ),
    )
    target: str | None = Field(
        default=None,
        description=(
            "Accessibility name of the element to check (tab/dialog/field/checkbox), usually "
            "the same as the step's target uia_name_hint. Null for 'cell_selected' and 'visual'."
        ),
    )
    expected: str | None = Field(
        default=None,
        description=(
            "For 'cell_selected': the cell/range reference, e.g. 'B5'. For 'value_equals': the "
            "expected value. Null otherwise."
        ),
    )


class TutorialStep(BaseModel):
    index: int = Field(description="0-based step number.")
    instruction: str = Field(
        description=(
            "A single imperative command - a physical action (Click, Type, Select, Press, "
            "Open, Choose, Drag, Scroll, Right-click). Exactly one action; name the precise "
            "element. Never an observation: do not begin with Look, Notice, Find, Locate, "
            "See, or Check. GOOD: 'Click the Developer tab.' BAD: 'Look at the ribbon.'"
        )
    )
    rationale: str = Field(
        description="One short sentence on why this step helps (shown only on the 'Why?' button)."
    )
    target: Target
    done_when: str = Field(
        description=(
            "The OBSERVABLE change visible on screen once the action succeeds - describe the "
            "app's state, never the user's action/perception. "
            "GOOD: 'The Record Macro dialog is open.' BAD: 'The user locates the button.'"
        )
    )
    done_signals: list[str] = Field(
        default_factory=list,
        description="1-3 concrete things visible on screen once the step is done.",
    )
    check: StepCheck = Field(
        default_factory=StepCheck,
        description="How to verify completion locally; defaults to visual (AI) when unsure.",
    )


class TutorialPlan(BaseModel):
    goal: str = Field(description="The user's goal, restated concisely.")
    app_name: str
    steps: list[TutorialStep] = Field(
        default_factory=list, description="Ordered, atomic steps that achieve the goal."
    )


class StepVerification(BaseModel):
    status: Literal["done", "not_done", "off_track", "unclear"] = Field(
        description=(
            "'done' only if the step's done condition is clearly visible in the screenshot; "
            "'not_done' if not yet; 'off_track' if the user went the wrong way; 'unclear' if "
            "you cannot tell from the screenshot."
        )
    )
    confidence: float = Field(description="0.0-1.0 confidence in the status.")
    observation: str = Field(description="One sentence describing the relevant screen state.")
    hint: str | None = Field(
        default=None,
        description="A one-sentence nudge toward completing the step (when not done/off track).",
    )
