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
