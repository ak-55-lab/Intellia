"""Ask anything.

Answers are grounded the same way the brief is: a deterministic evidence bundle
plus already-computed metrics go in, prose comes back. When the question is
clearly asking for a chart or table, the answer carries a generated insight the
user can pin to the canvas -- which is the answer-to-widget move.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Dict, Optional

from intellia.ai.prompts import knowledge, tasks
from intellia.ai.service import AIService
from intellia.config.personas import Persona
from intellia.data.scope import Scope
from intellia.models.ai import Answer
from intellia.services.context_service import ContextService
from intellia.services.metrics_service import MetricsService
from intellia.utils.dates import quarter_label
from intellia.utils.formatting import money, multiple, percent

# Deciding whether to run text to SQL fails OPEN. The engine is general: it reads
# the semantic layer and the worked examples and writes its own query, so the only
# turns worth skipping are the ones no query can answer. This used to be an
# allowlist of phrasings ("by rep", "by stage", "by account", "by industry"), which
# refused "give me customers ARR by region" without the engine ever seeing it,
# purely because that dimension had not been enumerated. Any new dimension, metric
# or phrasing broke it the same way, so the list is gone.
#
# Getting this wrong in the permissive direction costs one model call, cached
# afterwards on the question, and a failed generation already falls back to the
# evidence bundle. Getting it wrong in the strict direction produces an answer
# that says the data is missing when it is sitting in the database.

# Greetings and acknowledgements. Nothing to query.
_SMALL_TALK = re.compile(
    r"^\s*(hi|hello|hey|thanks|thank you|ok|okay|got it|nice|cool|yes|no|sure)"
    r"\b[\s!.?]*$", re.IGNORECASE)

# Asking the assistant to perform an action rather than to report a number.
_ACTION_REQUEST = re.compile(
    r"\b(draft|write|send|reply|respond|schedule|book|remind|log a|add a task|"
    r"set up|follow up with)\b", re.IGNORECASE)

# Asking for judgement, which the brief and the evidence bundle answer.
_ADVICE = re.compile(r"^\s*(what|who|how|where)\s+should\s+i\b", re.IGNORECASE)

# An action phrased around a breakdown still needs the rows, so these win over
# _ACTION_REQUEST. Deliberately broad: grouping, ranking and aggregate words in
# any combination, not a fixed set of dimension names.
_DATA_SHAPED = re.compile(
    r"\b(by|per|top|bottom|worst|best|total|sum|average|avg|median|count|"
    r"how many|how much|trend|compare|comparison|breakdown|break down|list|rank|"
    r"ranked|distribution|split|versus|vs|across|between)\b", re.IGNORECASE)


def wants_insight(question: str) -> bool:
    """Whether this turn should attempt text to SQL before answering.

    Returns True unless the question is clearly something a query cannot answer.
    The engine decides what it can and cannot express; this only avoids paying
    for a call that has no chance of helping.
    """
    text = (question or "").strip()
    if len(text) < 3:
        return False
    if _SMALL_TALK.match(text):
        return False
    if _ADVICE.match(text) and not _DATA_SHAPED.search(text):
        return False
    if _ACTION_REQUEST.search(text) and not _DATA_SHAPED.search(text):
        return False
    return True


class AskService:
    def __init__(self, ai: AIService, context: ContextService,
                 metrics: MetricsService) -> None:
        self.ai = ai
        self.context = context
        self.metrics = metrics

    def _metrics_summary(self, scope: Scope, as_of: date) -> str:
        s = self.metrics.summary(scope, as_of)
        return "\n".join([
            "- Open pipeline closing {}: {}".format(quarter_label(as_of),
                                                    money(s["open_pipeline"])),
            "- Bookings quarter to date: {}".format(money(s["bookings_qtd"])),
            "- Open deals: {:.0f}".format(s["open_deals"]),
            "- Average open deal size: {}".format(money(s["avg_deal_size"])),
            "- Win rate YTD (revenue-weighted): {}".format(percent(s["win_rate"])),
            "- Pipeline coverage: {}".format(multiple(s["coverage"])),
            "- Quota attainment this quarter: {}".format(percent(s["attainment"])),
        ])

    def _fallback(self, scope: Scope, as_of: date, question: str) -> Dict[str, Any]:
        s = self.metrics.summary(scope, as_of)
        return {
            "text": (
                "Here is where {scope} stands right now: {pipe} of open pipeline "
                "closing in {q}, {book} booked so far this quarter, and {deals:.0f} "
                "open deals at an average size of {avg}. Win rate year to date is "
                "{wr}. Open a specific insight for the detail behind any of these."
            ).format(scope=scope.label.lower(), pipe=money(s["open_pipeline"]),
                     q=quarter_label(as_of), book=money(s["bookings_qtd"]),
                     deals=s["open_deals"], avg=money(s["avg_deal_size"]),
                     wr=percent(s["win_rate"])),
            "follow_ups": ["Which deals are most likely to slip?",
                           "Show pipeline by stage"],
            "generated_by": "prepared",
        }

    def ask(self, question: str, scope: Scope, persona: Persona, as_of: date,
            result_table: str = "") -> Optional[Answer]:
        """Answer one question.

        ``result_table`` is the markdown rendering of a text-to-SQL result the
        caller has already executed. Passing it is what stops the answer and the
        chart beside it disagreeing: without the rows, the model correctly says it
        only has totals, while the chart under it shows the breakdown. The rows
        are the authority, and the model is told so.
        """
        bundle = self.context.for_day(scope, as_of)
        answer = self.ai.run(
            task=tasks.ASK,
            system=tasks.ask_system(persona.label, persona.role_label,
                                    as_of.isoformat(), scope.label),
            user=tasks.ask_user(question, bundle.to_prompt_markdown(),
                                self._metrics_summary(scope, as_of), result_table),
            cacheable_system=knowledge.narrative_knowledge(),
            cache_inputs={"q": question.strip().lower(),
                          "context": bundle.context_hash(),
                          "rows": result_table[:2000]},
            fallback=lambda: self._fallback(scope, as_of, question),
            persona_id=persona.id,
        )
        if answer is not None:
            answer.generated_by = self.ai.model_for(tasks.ASK)
        return answer


def frame_to_markdown(frame: Any, limit: int = 40) -> str:
    """A query result as a small markdown table for the prompt.

    Capped because a wide result would crowd out the evidence bundle, and the
    answer only ever needs to describe the shape and the leaders.
    """
    if frame is None or getattr(frame, "empty", True):
        return ""
    shown = frame.head(limit)
    header = "| " + " | ".join(str(c) for c in shown.columns) + " |"
    rule = "| " + " | ".join("---" for _ in shown.columns) + " |"
    rows = [
        "| " + " | ".join(
            "{:,.2f}".format(v).rstrip("0").rstrip(".") if isinstance(v, float)
            else str(v) for v in record) + " |"
        for record in shown.itertuples(index=False, name=None)
    ]
    note = ("\n\n({} more rows not shown)".format(len(frame) - len(shown))
            if len(frame) > len(shown) else "")
    return "\n".join([header, rule] + rows) + note
