"""Structured AI outputs.

Every LLM task returns one of these. They are validated by ``intellia.ai.structured``
before anything reaches the render path -- the model never emits free-form prose into a
component.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

BRIEF_KINDS = ("priority", "decision", "opportunity", "risk", "followup")


@dataclass
class BriefItem:
    kind: str               # one of BRIEF_KINDS
    title: str
    detail: str
    ref_type: str = ""      # deal | account | meeting | signal | task | email
    ref_id: str = ""
    urgency: str = "medium"  # high | medium | low
    suggested_action: str = ""


@dataclass
class DailyBrief:
    headline: str
    summary: str
    items: List[BriefItem] = field(default_factory=list)
    generated_by: str = "mock"
    generated_at: str = ""


@dataclass
class TalkingPoint:
    point: str
    rationale: str = ""
    ref_id: str = ""


@dataclass
class MeetingRisk:
    risk: str
    mitigation: str = ""


@dataclass
class NextStep:
    action: str
    owner: str = ""
    due_date: str = ""


@dataclass
class MeetingPrep:
    objective: str
    desired_outcomes: List[str] = field(default_factory=list)
    context: str = ""
    talking_points: List[TalkingPoint] = field(default_factory=list)
    risks: List[MeetingRisk] = field(default_factory=list)
    recommended_next_step: Optional[NextStep] = None
    generated_by: str = "mock"


@dataclass
class ActionExplanation:
    what_happened: str
    why_it_matters: str
    recommended_action: str
    generated_by: str = "mock"


@dataclass
class EmailDraft:
    subject: str
    body: str
    to: str = ""
    generated_by: str = "mock"


@dataclass
class GeneratedInsight:
    """The SQL-generation task's structured output."""

    title: str
    description: str
    sql: str
    visualization: str = "table"
    x: str = ""
    y: str = ""
    unit: str = "#"
    calculation: str = ""
    refresh: str = "Hourly"


@dataclass
class Answer:
    text: str
    follow_ups: List[str] = field(default_factory=list)
    insight: Optional[GeneratedInsight] = None
    generated_by: str = "mock"
