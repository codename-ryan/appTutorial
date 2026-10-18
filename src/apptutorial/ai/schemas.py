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


class TutorialPlan(BaseModel):
    goal: str = Field(description="The user's goal, restated concisely.")
    app_name: str
    steps: list[TutorialStep] = Field(
        default_factory=list, description="Ordered, atomic steps that achieve the goal."
    )
