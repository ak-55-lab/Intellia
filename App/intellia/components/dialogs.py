"""Dialogs: every panel that opens over the canvas.

Two shapes, and the difference is deliberate:

* **Medium cards** for reading: meeting prep, meeting recap, action detail. Wide
  enough for two columns, small enough that the canvas stays visible around it.
* **Medium authoring flows**: create with AI, edit with AI, add from the library.

Widget provenance is the one thing that does NOT open here. It is already
computed, so it opens in a popover beside its own ⓘ (``primitives.info_popover``)
instead of taking over the screen.

Streamlit allows only ONE dialog per script run and they cannot nest. Components
therefore never call ``st.dialog``: they set intent via ``session.set_dialog(...)``
and ``app.py`` runs a single dispatcher at the very end. This is the only
structure that cannot violate the one-dialog rule as the app grows. It also means
the trigger must not live inside a fragment, or the intent is set and no
dispatcher ever runs.

Every dialog passes ``on_dismiss=session.clear_dialog``. With the default
(``"ignore"``) the intent survives the dismissal, so the dialog reopens on the
next unrelated rerun: escape and the close button appear not to work. Clearing
the intent on dismissal is what actually closes them.
"""

from __future__ import annotations

from typing import Any, List, Sequence

import streamlit as st

from intellia.actions.executor import ACTION_LABELS
from intellia.components import primitives as ui
from intellia.state import session
from intellia.utils.dates import relative_day
from intellia.utils.formatting import esc, money, truncate

CREATE_EXAMPLES = [
    "Pipeline by rep versus quota this quarter",
    "Accounts with the most open pipeline",
    "Bookings by industry this year",
    "Average deal size by stage",
]


# -- meeting prep and recap --------------------------------------------------------------

def meeting_dialog(meeting: Any, build) -> None:
    """Pre-call brief, or the recap once the meeting is done.

    Capped lists and two columns, so it is a card to scan rather than a document
    to scroll. The model is asked for exactly this much and the render caps it
    again, because a long prep is a prep nobody reads before the call.
    """
    title = "Recap" if meeting.is_completed else "Prep"

    @st.dialog(title, width="medium", on_dismiss=session.clear_dialog)
    def _dialog() -> None:
        st.html('<p class="ix-card-title">{t}</p><p class="ix-meta">{m}</p>'.format(
            t=esc(meeting.title),
            m=esc("{} · {} · {} min".format(meeting.time_label, meeting.meeting_type,
                                            meeting.duration_minutes))))

        placeholder = st.empty()
        with placeholder.container():
            ui.skeleton(rows=3, height=11)
        prep = build()
        placeholder.empty()

        if prep is None:
            ui.error_card("We could not prepare this meeting.",
                          "The underlying records are still on the card.")
            return

        # Talking points is always the longest block, so it anchors the right
        # column on its own and the short blocks stack on the left. Split by
        # length rather than by category, or one column runs out early.
        left = [ui.text_section("Objective", truncate(prep.objective, 190)),
                ui.bullet_section("Outcomes", prep.desired_outcomes[:3])]
        right = [_points_html(prep.talking_points[:3]), _risks_html(prep.risks[:2])]

        st.html('<div class="ix-dialog-cols"><div>{l}</div><div>{r}</div></div>'.format(
            l="".join(b for b in left if b), r="".join(b for b in right if b)))
        st.html(_next_step_html(prep))
        st.html(ui.card_footer("Prepared by {}".format(prep.generated_by)))

    _dialog()


def _next_step_html(prep: Any) -> str:
    step = prep.recommended_next_step
    if not step:
        return ""
    detail = " · ".join(x for x in (step.owner, step.due_date) if x)
    return ('<div class="ix-section"><p class="ix-section-label">Next step</p>'
            '<p>{a}</p>{d}</div>').format(
        a=esc(step.action),
        d='<p class="ix-meta" style="margin-top:3px">{}</p>'.format(
            esc(detail)) if detail else "")


def _points_html(points: Sequence[Any]) -> str:
    if not points:
        return ""
    items = "".join(
        "<li>{}{}</li>".format(
            esc(p.point),
            '<br><span class="ix-rationale">{}</span>'.format(
                esc(truncate(p.rationale, 90))) if p.rationale else "")
        for p in points)
    return ('<div class="ix-section"><p class="ix-section-label">Talking points</p>'
            "<ol>{}</ol></div>").format(items)


def _risks_html(risks: Sequence[Any]) -> str:
    if not risks:
        return ""
    items = "".join(
        "<li>{}{}</li>".format(
            esc(r.risk),
            '<br><span class="ix-rationale">{}</span>'.format(
                esc(truncate(r.mitigation, 90))) if r.mitigation else "")
        for r in risks)
    return ('<div class="ix-section"><p class="ix-section-label">Watch for</p>'
            "<ul>{}</ul></div>").format(items)


# -- action detail -----------------------------------------------------------------------

def action_dialog(action: Any, explain, execute) -> None:
    """Why it surfaced, then the one control that acts on it."""

    @st.dialog("Action", width="medium", on_dismiss=session.clear_dialog)
    def _dialog() -> None:
        bits = [action.source_display]
        if action.account_name:
            bits.append(action.account_name)
        if action.amount:
            bits.append(money(action.amount))
        if action.due_date:
            bits.append(relative_day(action.due_date))
        st.html('<p class="ix-card-title">{t}</p><p class="ix-meta">{m}</p>'.format(
            t=esc(action.title), m=esc(" · ".join(bits))))

        placeholder = st.empty()
        with placeholder.container():
            ui.skeleton(rows=2, height=11)
        detail = explain()
        placeholder.empty()

        if detail is not None:
            st.html('<div class="ix-dialog-cols">{a}{b}</div>{c}'.format(
                a=ui.text_section("What happened", truncate(detail.what_happened, 170)),
                b=ui.text_section("Why it matters", truncate(detail.why_it_matters, 170)),
                c=ui.text_section("Recommended", truncate(detail.recommended_action, 170))))
        else:
            st.html(ui.text_section("Why this surfaced", action.why))

        done = session.executed(action.key)
        if done:
            st.html('<div style="margin:6px 0 0">{}</div>'.format(
                ui.chip(done.get("summary", "Done"), "good")))
            if done.get("draft"):
                with st.expander("View draft"):
                    st.code(done["draft"], language="text", wrap_lines=True)
            st.html(ui.card_footer("Prototype. Nothing was sent."))
            return

        _execute_row(action, execute)
        st.html(ui.card_footer("Prototype. Nothing is sent from this screen."))

    _dialog()


def _execute_row(action: Any, execute) -> None:
    options = [ACTION_LABELS.get(k, k) for k in _supported(action)]
    row = st.container(key="row-exec-{}".format(action.key.replace(":", "-")),
                       horizontal=True, vertical_alignment="center")
    with row:
        chosen_label = st.segmented_control(
            "Execution", options, default=options[0],
            key="exec-mode-{}".format(action.key), label_visibility="collapsed")
        run = st.button("Run", key="do-{}".format(action.key), type="primary",
                        icon=":material/play_arrow:")

    if not run:
        return
    chosen = _from_label(chosen_label or options[0], action)
    with st.status("Preparing", expanded=True) as status:
        result, draft = execute(chosen)
        for step in result.steps:
            st.write(step)
        status.update(label=result.summary, state="complete", expanded=False)
    session.mark_executed(action.key, {"summary": result.summary,
                                       "detail": result.detail, "draft": draft})
    st.toast(result.summary, icon=":material/check_circle:")
    st.rerun()


def _supported(action) -> List[str]:
    base = [action.default_action_type]
    for kind in ("draft_email", "update_crm", "create_task", "send_recap"):
        if kind not in base:
            base.append(kind)
    return base


def _from_label(label: str, action) -> str:
    for key in _supported(action):
        if ACTION_LABELS.get(key, key) == label:
            return key
    return action.default_action_type


# -- create with AI --------------------------------------------------------------------

def create_insight_dialog(generate, save) -> None:
    @st.dialog("Create an insight", width="medium", on_dismiss=session.clear_dialog)
    def _dialog() -> None:
        st.html('<p class="ix-card-sub">Describe what you want. Intellia writes the '
                'query once and reuses it, so every later refresh is free.</p>')

        question = st.text_area(
            "Describe the insight", key="create-q", height=78,
            placeholder="e.g. pipeline by rep versus quota this quarter",
            label_visibility="collapsed")

        st.html('<p class="ix-section-label">Examples</p>')
        for i, example in enumerate(CREATE_EXAMPLES):
            st.button(example, key="ex-{}".format(i), type="tertiary",
                      on_click=lambda t=example: st.session_state.update({"create-q": t}))

        candidate = session.edit_candidate()

        if st.button("Generate", type="primary", key="do-create",
                     icon=":material/auto_awesome:",
                     disabled=not (question or "").strip()):
            with st.status("Reading your request", expanded=False) as status:
                try:
                    status.update(label="Selecting data sources")
                    config, rendered = generate(question)
                    status.update(label="Writing the query")
                    session.set_edit_candidate((config, rendered))
                    status.update(label="Ready", state="complete")
                except Exception as exc:
                    status.update(label="Could not build that one", state="error")
                    ui.error_card(
                        "I could not build that insight from the available data.",
                        getattr(exc, "user_message", None)
                        or "Try pipeline by rep, by stage, or by account.")
                    return
            st.rerun()

        if candidate:
            config, rendered = candidate
            st.html('<div style="border-top:1px solid var(--border);margin:12px 0 8px">'
                    '</div><p class="ix-card-title">{}</p>'
                    '<p class="ix-card-sub">{}</p>'.format(
                        esc(config.title), esc(config.description)))
            # An empty result used to render nothing between the description and
            # the query, so the only way to discover that a card would be blank was
            # to add it to the canvas and look. Say it here, where Discard is one
            # click away and the query is open for inspection.
            if not rendered.ok:
                ui.empty_state("That query could not run.",
                               "Open Query below to see what was written.")
            elif rendered.frame.empty:
                ui.empty_state(
                    "This returns no rows right now.",
                    "The query is valid but nothing matches it today. Check the "
                    "wording below, or add it anyway if you expect rows later.")
            else:
                st.dataframe(rendered.frame.head(6), hide_index=True, width="stretch")
                st.html('<p class="ix-card-sub">{}</p>'.format(
                    esc("{:,} row{} returned.".format(
                        len(rendered.frame), "" if len(rendered.frame) == 1 else "s"))))
            with st.expander("Query"):
                st.code(config.generated_sql, language="sql", wrap_lines=True)

            row = st.container(key="row-create-actions", horizontal=True)
            with row:
                if st.button("Add to canvas", type="primary", key="save-created"):
                    save(config)
                    session.set_edit_candidate(None)
                    session.clear_dialog()
                    st.toast("Insight added to your canvas", icon=":material/check_circle:")
                    st.rerun()
                if st.button("Discard", type="tertiary", key="discard-created"):
                    session.set_edit_candidate(None)
                    st.rerun()

    _dialog()


# -- edit with AI ----------------------------------------------------------------------

def edit_insight_dialog(config, apply_edit, save) -> None:
    @st.dialog("Edit with AI", width="medium", on_dismiss=session.clear_dialog)
    def _dialog() -> None:
        st.html('<p class="ix-card-title">{}</p>'
                '<p class="ix-card-sub">Describe the change in plain English. If it '
                'does not work, the current version stays exactly as it is.</p>'.format(
                    esc(config.title)))

        instruction = st.text_area(
            "Change", key="edit-q", height=72, label_visibility="collapsed",
            placeholder="e.g. only reps below 3x coverage")

        candidate = session.edit_candidate()

        if st.button("Apply change", type="primary", key="do-edit",
                     icon=":material/auto_awesome:",
                     disabled=not (instruction or "").strip()):
            with st.status("Rewriting the query", expanded=False) as status:
                try:
                    new_config, rendered = apply_edit(instruction)
                    session.set_edit_candidate((new_config, rendered, instruction))
                    status.update(label="Ready to review", state="complete")
                except Exception as exc:
                    status.update(label="Change not applied", state="error")
                    ui.error_card("That change did not work, so I kept the current "
                                  "version.", getattr(exc, "user_message", "") or "")
                    return
            st.rerun()

        if candidate and len(candidate) == 3:
            new_config, rendered, note = candidate
            st.html('<div style="border-top:1px solid var(--border);margin:12px 0 8px">'
                    '</div>')
            if rendered.ok and not rendered.frame.empty:
                st.dataframe(rendered.frame.head(6), hide_index=True, width="stretch")
            with st.expander("Before and after"):
                st.html('<p class="ix-section-label">Before</p>')
                st.code(config.generated_sql, language="sql", wrap_lines=True)
                st.html('<p class="ix-section-label">After</p>')
                st.code(new_config.generated_sql, language="sql", wrap_lines=True)

            row = st.container(key="row-edit-actions", horizontal=True)
            with row:
                if st.button("Accept", type="primary", key="accept-edit"):
                    save(new_config, note)
                    session.set_edit_candidate(None)
                    session.clear_dialog()
                    st.toast("Updated to v{}".format(new_config.version),
                              icon=":material/check_circle:")
                    st.rerun()
                if st.button("Discard", type="tertiary", key="discard-edit"):
                    session.set_edit_candidate(None)
                    st.rerun()

        st.html('<p class="ix-meta" style="margin-top:12px">On v{}. Every edit appends '
                'a version; nothing is overwritten.</p>'.format(config.version))

    _dialog()


# -- add from library ------------------------------------------------------------------

def add_widget_dialog(hidden: Sequence[Any], on_add) -> None:
    @st.dialog("Add to your canvas", width="medium", on_dismiss=session.clear_dialog)
    def _dialog() -> None:
        if not hidden:
            ui.empty_state("Everything is already on your canvas.",
                           "Use create with AI to build something new.")
            return
        st.html('<p class="ix-card-sub">Components available for your role.</p>')
        for widget in hidden:
            row = st.container(key="row-head-add-{}".format(widget.key.replace(".", "-")),
                               horizontal=True, vertical_alignment="center")
            with row:
                st.html('<div><b style="font-size:12.5px">{t}</b>'
                        '<div class="ix-meta">{s}</div></div>'.format(
                            t=esc(widget.title),
                            s=esc(truncate(widget.subtitle or widget.category, 62))))
                st.button("Add", key="add-{}".format(widget.key),
                          icon=":material/add:", on_click=on_add, args=(widget.key,))

    _dialog()
