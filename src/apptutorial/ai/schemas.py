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

    description: str  # e.g. "the Record Macro button on the Developer tab"
    uia_name_hint: str | None = None  # exact accessibility label, when known
    uia_role_hint: str | None = None  # e.g. "Button", "TabItem"


class TutorialStep(BaseModel):
    index: int
    instruction: str  # what to do
    rationale: str  # one sentence on why (shown on the "Why?" button)
    target: Target
    done_when: str  # observable condition that means the step is complete
    done_signals: list[str] = Field(default_factory=list)  # things visible when done


class TutorialPlan(BaseModel):
    goal: str
    app_name: str
    steps: list[TutorialStep] = Field(default_factory=list)
