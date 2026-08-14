"""Daily Brief.

Deterministic: candidate assembly, the metric numbers, and post-hoc reference
validation. LLM: ranking and prose only. Any item whose ``ref_id`` is not in the
evidence set is dropped before render, which is what makes the brief trustworthy
and the mock fallback acceptable.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
from typing import Any, Dict, List, Optional

from intellia.ai.prompts import knowledge, tasks
from intellia.ai.service import AIService
from intellia.config.personas import Persona
from intellia.data.scope import Scope
from intellia.models.ai import BRIEF_KINDS, BriefItem, DailyBrief
from intellia.services.context_service import ContextService
from intellia.services.metrics_service import MetricsService
from intellia.utils.dates import quarter_label, relative_day
from intellia.utils.formatting import money, multiple, percent
from intellia.utils.logging import get_logger

log = get_logger("brief")


class DailyBriefService:
    def __init__(self, ai: AIService, context: ContextService,
                 metrics: MetricsService) -> None:
        self.ai = ai
        self.context = context
        self.metrics = metrics

    # -- deterministic inputs ----------------------------------------------------------

    def _metrics_summary(self, scope: Scope, as_of: date) -> str:
        s = self.metrics.summary(scope, as_of)
        return "\n".join([
            "- Open pipeline closing {}: {}".format(quarter_label(as_of),
                                                    money(s["open_pipeline"])),
            "- Bookings quarter to date: {}".format(money(s["bookings_qtd"])),
            "- Open deals: {:.0f}".format(s["open_deals"]),
            "- Win rate YTD (revenue-weighted): {}".format(percent(s["win_rate"])),
            "- Pipeline coverage: {}".format(multiple(s["coverage"])),
            "- Quota attainment this quarter: {}".format(percent(s["attainment"])),
        ])

    def _fallback(self, scope: Scope, as_of: date, persona: Persona) -> Dict[str, Any]:
        """Deterministic brief built from the same real records the live path sees."""
        bundle = self.context.for_day(scope, as_of)
        items: List[Dict[str, Any]] = []

        for signal in bundle.signals[:2]:
            items.append(asdict(BriefItem(
                kind="opportunity" if signal.severity != "High" else "priority",
                title="{}: {}".format(signal.account_name, signal.signal_title),
                detail="Signal scored {} and is still unactioned. {}".format(
                    signal.score, signal.action_recommended),
                ref_type="signal", ref_id=signal.signal_id,
                urgency="high" if signal.score >= 85 else "medium",
                suggested_action=signal.action_recommended,
            )))

        for meeting in [m for m in bundle.meetings if not m.is_completed][:2]:
            items.append(asdict(BriefItem(
                kind="priority",
                title="{} at {}".format(meeting.title, meeting.time_label),
                detail=meeting.agenda or "Scheduled for today.",
                ref_type="meeting", ref_id=meeting.meeting_id,
                urgency="high",
                suggested_action="Open the prep brief before the call.",
            )))

        for email in bundle.emails[:1]:
            items.append(asdict(BriefItem(
                kind="followup",
                title="Unanswered reply from {}".format(
                    email.contact_name or email.account_name),
                detail="\"{}\" is still waiting on a response (sentiment {:+.2f}).".format(
                    email.subject, email.sentiment_score),
                ref_type="email", ref_id=email.email_id, urgency="medium",
                suggested_action="Reply today.",
            )))

        overdue = [t for t in bundle.tasks if t.due_date and t.due_date < as_of]
        for task in overdue[:1]:
            items.append(asdict(BriefItem(
                kind="risk", title=task.title,
                detail="Overdue ({}) on {}.".format(
                    relative_day(task.due_date), task.account_name or "your queue"),
                ref_type="task", ref_id=task.task_id, urgency="high",
                suggested_action="Clear it or move the date.",
            )))

        scheduled = len([m for m in bundle.meetings if not m.is_completed])
        return {
            "headline": "{} meeting{} today and {} signal{} worth acting on.".format(
                scheduled, "" if scheduled == 1 else "s",
                len(bundle.signals), "" if len(bundle.signals) == 1 else "s"),
            "summary": ("Your day is shaped by the meetings on the calendar and the "
                        "signals that landed since yesterday. Clear the overdue items "
                        "before your first call."),
            "items": items,
            "generated_by": "prepared",
            "generated_at": as_of.isoformat(),
        }

    # -- public ------------------------------------------------------------------------

    def generate(self, scope: Scope, persona: Persona, as_of: date) -> Optional[DailyBrief]:
        bundle = self.context.for_day(scope, as_of)
        valid_refs = bundle.valid_ref_ids()
        metrics_summary = self._metrics_summary(scope, as_of)

        brief = self.ai.run(
            task=tasks.DAILY_BRIEF,
            system=tasks.daily_brief_system(
                persona.label, persona.role_label, persona.brief_variant, as_of.isoformat()),
            user=tasks.daily_brief_user(bundle.to_prompt_markdown(), metrics_summary),
            cacheable_system=knowledge.narrative_knowledge(),
            cache_inputs={"context": bundle.context_hash(), "variant": persona.brief_variant},
            fallback=lambda: self._fallback(scope, as_of, persona),
            persona_id=persona.id,
        )
        if brief is None:
            return None

        # Post-hoc reference validation: anything the model invented is dropped.
        kept: List[BriefItem] = []
        for item in brief.items:
            if item.kind not in BRIEF_KINDS:
                item.kind = "priority"
            if item.ref_id and item.ref_id not in valid_refs:
                log.warning("Dropping brief item with unknown ref_id %s", item.ref_id)
                continue
            if item.ref_id:
                item.ref_type = valid_refs[item.ref_id]
            kept.append(item)

        brief.items = kept[:6]
        brief.generated_by = self.ai.model_for(tasks.DAILY_BRIEF)
        return brief
