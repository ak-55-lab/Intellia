"""Persona registry -- pure data.

Adding a persona is one dict entry. Nothing branches on persona id: scoping flows through
``scope_kind`` and the experience differs only by ``default_widgets`` and ``brief_variant``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class Persona:
    id: str
    user_id: str
    label: str
    role_label: str
    scope_kind: str            # own_book | team | all
    brief_variant: str
    scope_label: str
    default_widgets: List[str] = field(default_factory=list)
    tagline: str = ""


# The bespoke panels are widgets too -- they appear in the composer and can be
# hidden like anything else, so they must be listed as defaults or they start off.
FOCUS_WIDGETS = [
    "component.daily_brief",
    "component.meetings",
    "component.actions",
]

REP_WIDGETS = FOCUS_WIDGETS + [
    "kpi.my_open_pipeline",
    "kpi.my_bookings_qtd",
    "kpi.my_quota_attainment",
    "insight.pipeline_by_stage",
    "insight.deals_closing",
    "insight.pipeline_trend",
    "insight.at_risk_deals",
    "insight.my_next_steps",
]

MANAGER_WIDGETS = FOCUS_WIDGETS + [
    "kpi.team_open_pipeline",
    "kpi.team_bookings_qtd",
    "kpi.team_win_rate",
    "insight.pipeline_by_rep",
    "insight.attainment_by_rep",
    "insight.coverage_by_rep",
    "insight.at_risk_deals",
    "insight.rep_activity",
]

PERSONA_REGISTRY: Dict[str, Persona] = {
    "rep": Persona(
        id="rep",
        user_id="USR-3002",
        label="Elena Benson",
        role_label="Senior Account Executive",
        scope_kind="own_book",
        brief_variant="rep",
        scope_label="Your book",
        default_widgets=REP_WIDGETS,
        tagline="Enterprise Sales · AMER",
    ),
    "manager": Persona(
        id="manager",
        user_id="USR-3003",
        label="James Clark",
        role_label="Sales Manager",
        scope_kind="team",
        brief_variant="manager",
        scope_label="Your team",
        default_widgets=MANAGER_WIDGETS,
        tagline="Enterprise Sales · AMER",
    ),
}

DEFAULT_PERSONA = "rep"


def get_persona(persona_id: str) -> Persona:
    return PERSONA_REGISTRY.get(persona_id, PERSONA_REGISTRY[DEFAULT_PERSONA])


