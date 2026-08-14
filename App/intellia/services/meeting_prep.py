"""Meeting Prep.

Deterministic: the context bundle. LLM: every narrative field. Cached per
meeting id + context hash, so re-opening the same prep is free.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
from typing import Any, Dict, Optional

from intellia.ai.prompts import knowledge, tasks
from intellia.ai.service import AIService
from intellia.config.personas import Persona
from intellia.data.scope import Scope
from intellia.models.ai import MeetingPrep, MeetingRisk, NextStep, TalkingPoint
from intellia.models.domain import Meeting
from intellia.services.context_service import ContextService
from intellia.utils.formatting import money
from intellia.utils.logging import get_logger

log = get_logger("prep")


class MeetingPrepService:
    def __init__(self, ai: AIService, context: ContextService) -> None:
        self.ai = ai
        self.context = context

    def _fallback(self, meeting: Meeting, bundle: Any) -> Dict[str, Any]:
        account = bundle.account
        deal = bundle.deal
        name = account.account_name if account else "the team"

        outcomes = ["Confirm the agenda and who owns each next step"]
        if deal:
            outcomes.append("Agree a close date for {} ({})".format(
                deal.deal_name, money(deal.amount)))
            if deal.next_step:
                outcomes.append(deal.next_step)
        outcomes.append("Leave with a scheduled follow-up")

        points = []
        for m in bundle.meetings[:1]:
            for kp in m.key_points[:2]:
                points.append(asdict(TalkingPoint(
                    point=kp, rationale="Raised in {}.".format(m.title),
                    ref_id=m.meeting_id)))
        for s in bundle.signals[:1]:
            points.append(asdict(TalkingPoint(
                point=s.signal_title,
                rationale=s.action_recommended, ref_id=s.signal_id)))
        if not points:
            points.append(asdict(TalkingPoint(
                point="Confirm priorities for the coming quarter",
                rationale="No recent recorded context to draw on.")))

        risks = []
        negative = [e for e in bundle.emails if e.sentiment_score < -0.2]
        if negative:
            risks.append(asdict(MeetingRisk(
                risk="Recent correspondence has turned negative.",
                mitigation="Open by naming the concern directly rather than presenting.")))
        if deal and deal.competitor:
            risks.append(asdict(MeetingRisk(
                risk="{} is in the evaluation.".format(deal.competitor),
                mitigation="Lead with the differentiators that matter to this buyer.")))
        if not risks:
            risks.append(asdict(MeetingRisk(
                risk="No executive sponsor confirmed.",
                mitigation="Ask who signs off before the call ends.")))

        return {
            "objective": "Move {} forward: {}".format(
                name, meeting.agenda or "align on next steps and confirm ownership."),
            "desired_outcomes": outcomes[:4],
            "context": "{} is a {} account{}. {}".format(
                name,
                account.status.lower() if account else "prospect",
                " with {} ARR".format(money(account.arr)) if account and account.arr else "",
                "The open opportunity is {} at {}, closing {}.".format(
                    deal.deal_name, money(deal.amount), deal.close_date)
                if deal else "There is no open opportunity on the account.",
            ),
            "talking_points": points[:4],
            "risks": risks[:3],
            "recommended_next_step": asdict(NextStep(
                action=(deal.next_step if deal and deal.next_step
                        else "Send a recap with agreed owners and dates"),
                owner="You",
                due_date=str(deal.next_step_due_date) if deal and deal.next_step_due_date else "",
            )),
            "generated_by": "prepared",
        }

    def generate(self, scope: Scope, persona: Persona, meeting: Meeting,
                 as_of: date) -> Optional[MeetingPrep]:
        bundle = self.context.for_meeting(scope, meeting)

        prep = self.ai.run(
            task=tasks.MEETING_PREP,
            system=tasks.meeting_prep_system(persona.label, as_of.isoformat()),
            user=tasks.meeting_prep_user(bundle.to_prompt_markdown()),
            cacheable_system=knowledge.narrative_knowledge(),
            cache_inputs={"meeting": meeting.meeting_id, "context": bundle.context_hash()},
            fallback=lambda: self._fallback(meeting, bundle),
            persona_id=persona.id,
        )
        if prep is None:
            return None
        prep.generated_by = self.ai.model_for(tasks.MEETING_PREP)
        return prep
