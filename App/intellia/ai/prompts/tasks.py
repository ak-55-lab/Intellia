"""Task specs and prompt builders.

Each task carries its own ``prompt_version``; bumping it invalidates exactly that
task's cache and nothing else.

Every prompt states the same hard rule: the model ranks, groups and writes prose
over an evidence set it is given. It never computes a number and never invents an
entity -- and each reference id it emits is validated against the evidence before
anything renders.
"""

from __future__ import annotations

from intellia.ai.llm_provider import TaskSpec
from intellia.config.settings import DEFAULT_MODEL, FAST_MODEL
from intellia.models.ai import (
    ActionExplanation, Answer, DailyBrief, EmailDraft, GeneratedInsight, MeetingPrep,
)

GROUNDING = (
    "Ground every statement in the evidence provided. Never invent an account, deal, "
    "meeting, person or number. Every ref_id you emit must appear verbatim in the "
    "evidence. Do not compute or restate metrics that are not given to you. "
    "Write in plain, specific business English: no filler, no hedging, no preamble. "
    "Never use an em dash or a double hyphen; use a comma, a colon or a full stop. "
    "Use sentence case for every title and label, not Title Case. "
    "Never print a record id in prose a person reads: name the account, the deal or "
    "the person instead. Ids belong in the ref_id fields, which is where they are "
    "validated."
)

# -- task registry ---------------------------------------------------------------------
# prompt_version is per task: bumping one invalidates that task's cache and
# nothing else.

DAILY_BRIEF = TaskSpec("daily_brief", DailyBrief, effort="medium",
                       max_tokens=8000, prompt_version="3", model=DEFAULT_MODEL)
MEETING_PREP = TaskSpec("meeting_prep", MeetingPrep, effort="medium",
                        max_tokens=8000, prompt_version="3", model=DEFAULT_MODEL)
ACTION_EXPLAIN = TaskSpec("action_explain", ActionExplanation, effort="low",
                          max_tokens=3000, prompt_version="3", model=FAST_MODEL)
EMAIL_DRAFT = TaskSpec("email_draft", EmailDraft, effort="low",
                       max_tokens=3000, prompt_version="2", model=FAST_MODEL)
INSIGHT_SQL = TaskSpec("insight_sql", GeneratedInsight, effort="low",
                       max_tokens=4000, prompt_version="5", model=FAST_MODEL)
# Low effort keeps the conversation feeling immediate. The answer is prose over
# rows that are already computed, so depth buys nothing here.
ASK = TaskSpec("ask", Answer, effort="low", max_tokens=3000, prompt_version="4",
               model=FAST_MODEL)


# -- daily brief -----------------------------------------------------------------------

def daily_brief_system(persona_label: str, role_label: str, variant: str,
                       reporting_date: str) -> str:
    audience = (
        "You are briefing an individual account executive on their own book of business."
        if variant == "rep" else
        "You are briefing a sales manager on their team's aggregate risk and momentum. "
        "Speak about reps and the team, not about a single deal in isolation."
    )
    return (
        "You write the morning brief inside Intellia, a revenue intelligence product.\n\n"
        "{audience}\n"
        "Reader: {label}, {role}. Today is {date}.\n\n"
        "This is read in fifteen seconds, so length is a hard constraint:\n"
        "- `headline`: one sentence, at most 16 words, naming the single most "
        "important thing today.\n"
        "- `summary`: ONE sentence, at most 24 words, framing the day. Not two.\n"
        "- exactly 4 items, each with a kind of exactly one of: priority, decision, "
        "opportunity, risk, followup.\n"
        "- item `title`: at most 7 words, naming the account.\n"
        "- item `detail`: ONE clause, at most 16 words, saying why it matters now. "
        "No restating the record, no reference ids in the prose.\n"
        "- leave `suggested_action` empty; the action queue already carries it.\n\n"
        "{grounding}"
    ).format(audience=audience, label=persona_label, role=role_label,
             date=reporting_date, grounding=GROUNDING)


def daily_brief_user(evidence: str, metrics_summary: str) -> str:
    return (
        "## Today's evidence\n\n{evidence}\n\n"
        "## Current numbers (already computed, quote them, do not recalculate)\n\n"
        "{metrics}\n\nWrite the brief. Stay inside the word limits."
    ).format(evidence=evidence or "No activity recorded for today.",
             metrics=metrics_summary)


# -- meeting prep ----------------------------------------------------------------------

def meeting_prep_system(persona_label: str, reporting_date: str) -> str:
    return (
        "You prepare executives for customer meetings inside Intellia.\n\n"
        "Reader: {label}. Today is {date}.\n\n"
        "This is scanned in the ninety seconds before the call, so length is a hard "
        "constraint:\n"
        "- `objective`: one sentence, at most 20 words.\n"
        "- `desired_outcomes`: exactly 3, at most 8 words each.\n"
        "- `talking_points`: exactly 3. `point` at most 12 words; `rationale` one "
        "short clause tied to the evidence.\n"
        "- `risks`: 1 or 2. `risk` at most 10 words; `mitigation` one short clause.\n"
        "- `recommended_next_step`: one concrete action with an owner.\n"
        "- leave `context` empty. The card already shows where things stand.\n\n"
        "{grounding}"
    ).format(label=persona_label, date=reporting_date, grounding=GROUNDING)


def meeting_prep_user(evidence: str) -> str:
    return (
        "## Evidence for this meeting\n\n{evidence}\n\n"
        "Write the prep. Stay inside the word limits."
    ).format(evidence=evidence)


# -- action explanation and email draft ------------------------------------------------

def action_explain_system(reporting_date: str) -> str:
    return (
        "You explain a single recommended action to a seller inside Intellia. "
        "Today is {date}.\n\n"
        "Three fields, ONE sentence each and at most 22 words each: what_happened "
        "(the facts that triggered this), why_it_matters (the consequence of not "
        "acting), recommended_action (exactly what to do next).\n\n{grounding}"
    ).format(date=reporting_date, grounding=GROUNDING)


def email_draft_system(sender_name: str, playbook_hint: str) -> str:
    hint = ("\n\nA relevant outreach playbook from the company's own guidance:\n"
            + playbook_hint) if playbook_hint else ""
    return (
        "You draft outbound sales email for {sender}, writing as them.\n\n"
        "Keep it under 140 words. No greeting fluff, no 'I hope this finds you well', "
        "no exclamation marks. Open with the reason for writing, reference something "
        "specific and true from the evidence, and close with one clear ask. "
        "The subject line is under 8 words and not clickbait.{hint}\n\n{grounding}"
    ).format(sender=sender_name, hint=hint, grounding=GROUNDING)


# -- text to SQL -----------------------------------------------------------------------

def insight_sql_system(schema_text: str, reporting_date: str, scope_label: str) -> str:
    return (
        "You turn a business question into ONE SQLite SELECT statement for Intellia.\n\n"
        "## Rules\n"
        "- Return a single SELECT (a leading WITH is allowed). No semicolon. "
        "No INSERT/UPDATE/DELETE/DDL/PRAGMA/ATTACH.\n"
        "- Use only the tables and columns listed below. Never qualify with `main.`.\n"
        "- Use explicit ISO date literals; today is {date}. Never use CURRENT_DATE.\n"
        "- Rows are already restricted to {scope}, so do NOT add an owner filter.\n"
        "- Alias every output column to a readable snake_case name.\n"
        "- Return at most 100 rows; add an explicit LIMIT for ranked lists.\n"
        "- Follow the metric definitions in the semantic layer exactly.\n\n"
        "## Available schema\n{schema}\n\n"
        "## Visualization\n"
        "Choose the one that fits the result shape: `metric` for a single number, "
        "`bar` or `hbar` for one dimension plus one measure, `line` for a time "
        "series, `donut` for a 3-5 way part-to-whole, `table` otherwise. Set `unit` to "
        "one of $, %, x or #.\n"
        "Select the measure the question is actually about. If you also return a row "
        "count, put the value measure FIRST, because that is what gets charted.\n"
        "- Period comparison: when the question asks for a change, growth, or a "
        "movement against last month, quarter or year, return ONE row with the "
        "current value FIRST and its baseline SECOND, and set the visualization "
        "to `metric`. Alias the baseline `prior_<period>_<measure>`, naming the "
        "period it steps back by: `pipeline_created`, then "
        "`prior_month_pipeline_created`. Return the two values and never the "
        "percentage itself: the card computes the movement, labels it from the "
        "period in that alias, and colours it.\n\n"
        "## Wording\n"
        "- `title`: at most 6 words in sentence case, not Title Case, and no em "
        "dash. Keep acronyms capitalised: ARR, QTD, YTD, ICP, CRM.\n"
        "- `description`: ONE sentence, at most 12 words, sentence case, saying "
        "what the card shows in business English. No column names, no table "
        "names, no date literals, no brackets, and no second clause about a "
        "comparison. It sits under the title in small type beside other cards, so "
        "it must read like `Open pipeline value at each stage of the sales "
        "process.`\n"
        "- `calculation`: one sentence for the reader who opens the definition "
        "panel. Every mechanical detail belongs here, not in `description`: the "
        "date field, the window, the filters and the exact formula."
    ).format(schema=schema_text, date=reporting_date, scope=scope_label)


def prior_turn_block(question: str, sql: str, viz: str) -> str:
    """The previous turn, for a follow-up that refers to it rather than restating it.

    Without this the generator sees one bare sentence, so "flip this to a donut"
    has no referent and it answers a question nobody asked.
    """
    if not question or not sql:
        return ""
    return (
        "## The turn before this one\n"
        "They asked: {q}\n"
        "Which produced this query, drawn as a {viz}:\n"
        "{sql}\n\n"
        "If the new question refers back to that result rather than naming its own "
        "subject (this, that, it, the same, flip, instead, break it down further, "
        "as a donut, add a column), then start from the query above and change only "
        "what was asked for, keeping the subject and the filters. If the new "
        "question names its own subject, ignore this section entirely.\n\n"
    ).format(q=question.strip(), sql=sql.strip(), viz=viz or "table")


def insight_sql_user(question: str, prior: str = "") -> str:
    return "{prior}Business question: {q}\n\nReturn the insight definition.".format(
        prior=prior, q=question)


# -- ask anything ----------------------------------------------------------------------

def ask_system(persona_label: str, role_label: str, reporting_date: str,
               scope_label: str) -> str:
    return (
        "You are Intellia, an AI assistant embedded in a revenue team's workspace.\n\n"
        "Reader: {label}, {role}. Scope: {scope}. Today is {date}.\n\n"
        "Answer directly and briefly: two to four sentences, no headers, no bullet "
        "lists unless enumerating three or more items. Lead with the answer, then the "
        "reason. Quote the numbers you were given and never compute new ones. "
        "If the question asks for data you were not given, say what you would need "
        "rather than guessing. Offer two short follow-up questions the reader might "
        "ask next, each under 8 words.\n\n{grounding}"
    ).format(label=persona_label, role=role_label, scope=scope_label,
             date=reporting_date, grounding=GROUNDING)


EMPTY_RESULT = "__no_rows__"


def ask_user(question: str, evidence: str, metrics_summary: str,
             result_table: str = "") -> str:
    if result_table == EMPTY_RESULT:
        # Zero rows is an answer, not an absence of data. Left to infer from a
        # blank slot the model reported that it had not been given account-level
        # figures at all, which is a different and untrue claim.
        rows = ("\n\n## Query result for this exact question (authoritative)\n\n"
                "The query ran against the reader's own scoped data and matched "
                "nothing: zero rows.\n\nSay so plainly. The answer is none, not "
                "that the data was unavailable to you. Do not say you lack the "
                "figures or would need another table.")
    elif result_table:
        rows = ("\n\n## Query result for this exact question (authoritative)\n\n{}\n\n"
                "These rows were produced by running SQL against the reader's own "
                "scoped data, and a chart of them is shown beside your answer. Read "
                "the answer off these rows. Never say you were not given the "
                "breakdown when it is here.".format(result_table))
    else:
        rows = ""
    return (
        "Question: {q}\n\n## Evidence available\n\n{evidence}\n\n"
        "## Current numbers\n\n{metrics}{rows}"
    ).format(q=question, evidence=evidence or "(none)", metrics=metrics_summary,
             rows=rows)
