"""The focus band: Daily brief, and Today (meetings plus actions in one widget).

Each is a pure render function taking already-built domain objects. No panel
touches the database, the AI service or session state.

Row buttons only raise intent. The prep, recap and action cards themselves live
in ``dialogs`` as medium cards, so a row stays a row: one small button, not a
panel that pushes the rest of the canvas down when it opens.
"""

from __future__ import annotations

from typing import Any, Callable, Optional, Sequence

import streamlit as st

from intellia.components import primitives as ui
from intellia.models.action import Action
from intellia.models.ai import DailyBrief
from intellia.models.domain import Meeting
from intellia.utils.dates import relative_day
from intellia.utils.formatting import esc, money, truncate

MEETING_TYPE_TONE = {"Renewal Review": "risk", "Negotiation": "caution"}
LIST_HEIGHT = 330
MAX_BRIEF_ITEMS = 4


# -- daily brief -----------------------------------------------------------------------

def render_brief(build: Callable[[], Optional[DailyBrief]], generated_label: str,
                 on_refresh: Callable[[], None],
                 info_pairs: Sequence[Any] = (),
                 controls: Sequence[Any] = ()) -> None:
    """``build`` is called after the card chrome is on screen.

    A live brief is the one slow thing on the canvas, so the header, the tools
    and a skeleton paint first and the prose lands into place. Passing the brief
    itself would block the whole page behind the model call.
    """
    with ui.card("brief"):
        head = st.container(key="row-head-brief", horizontal=True,
                            vertical_alignment="top")
        with head:
            st.html(ui.card_header("Daily brief", "What changed and what it means"))
            with st.container(key="icon-refresh-brief"):
                st.button("", key="refresh-brief", icon=":material/refresh:",
                          help="Regenerate the brief", on_click=on_refresh)
            if info_pairs:
                ui.info_popover("brief", "Daily brief", info_pairs)
            if controls:
                ui.control_strip("brief", controls)

        placeholder = st.empty()
        with placeholder.container():
            ui.skeleton(rows=3, height=12)
        brief = build()
        placeholder.empty()

        if brief is None:
            ui.empty_state("The brief is not available right now.",
                           "Everything else on this page still works.")
            st.html(ui.card_footer("Calendar, mail, CRM and signals"))
            return

        st.html(
            '<p class="ix-brief-head">{h}</p>'
            '<p class="ix-brief-sum">{s}</p>'.format(
                h=esc(brief.headline), s=esc(truncate(brief.summary, 190)))
        )

        if brief.items:
            # One st.html call for every item: fewer DOM containers means the
            # badge column stays aligned and spacing stays controllable.
            rows = [
                '<div class="ix-brief-item"><div>{badge}</div>'
                '<p class="ix-brief-text"><b>{title}</b> {detail}</p></div>'.format(
                    badge=ui.badge(item.kind), title=esc(item.title),
                    detail=esc(truncate(item.detail, 110)))
                for item in brief.items[:MAX_BRIEF_ITEMS]
            ]
            st.html('<div class="ix-brief-list">{}</div>'.format("".join(rows)))

        st.html(ui.card_footer("Calendar, mail, CRM and signals · {}".format(
            generated_label)))


# -- today: meetings and actions in one widget -------------------------------------------

# Where a meeting is held decides whether "join" means anything. A room does not
# have a join link, so it does not get a button.
JOIN_TARGETS = {
    "Zoom": "Zoom",
    "Microsoft Teams": "Teams",
    "Google Meet": "Meet",
}


def render_today(meetings: Sequence[Meeting], actions: Sequence[Action],
                 attendee_names, executed_lookup,
                 show_meetings: bool, show_actions: bool,
                 on_meeting: Callable[[str], None],
                 on_action: Callable[[str], None],
                 on_join: Optional[Callable[[str], None]] = None,
                 info_pairs: Sequence[Any] = (),
                 controls: Sequence[Any] = ()) -> None:
    """Two equal, independently scrolling columns inside a single card."""
    with ui.card("today"):
        head = st.container(key="row-head-today", horizontal=True,
                            vertical_alignment="top")
        with head:
            st.html(ui.card_header("Today", "Your calendar and your queue, side by side"))
            if info_pairs:
                ui.info_popover("today", "Today", info_pairs)
            if controls:
                ui.control_strip("today", controls)

        if show_meetings and show_actions:
            left, right = st.columns(2, gap="medium")
        elif show_meetings:
            left, right = st.container(), None
        else:
            left, right = None, st.container()

        if left is not None and show_meetings:
            with left:
                _meetings_column(meetings, attendee_names, on_meeting, on_join)
        if right is not None and show_actions:
            with right:
                _actions_column(actions, executed_lookup, on_action)

        st.html(ui.card_footer("Outlook calendar, mail, CRM and signals"))


def _list_head(label: str, count: int, note: str) -> None:
    st.html(
        '<div class="ix-list-head"><span class="ix-eyebrow">{l}</span>'
        '<span class="ix-count">{c}</span>'
        '<span class="ix-meta" style="margin-left:auto">{n}</span></div>'.format(
            l=esc(label), c=count, n=esc(note))
    )


def _meetings_column(meetings: Sequence[Meeting], attendee_names,
                     on_meeting: Callable[[str], None], on_join=None) -> None:
    _list_head("Meetings", len(meetings), "prep or recap")
    if not meetings:
        ui.empty_state("No meetings today.", "Your calendar is clear.")
        return

    with st.container(key="scroll-meetings", height=LIST_HEIGHT, border=False):
        for meeting in meetings:
            _meeting_row(meeting, attendee_names, on_meeting, on_join)


def _meeting_row(meeting: Meeting, attendee_names, on_meeting, on_join=None) -> None:
    tone = MEETING_TYPE_TONE.get(meeting.meeting_type, "")
    bits = [b for b in (meeting.account_name, meeting.location) if b]
    if meeting.attendee_count:
        bits.append("{} attending".format(meeting.attendee_count))

    with st.container(key="lrow-m-{}".format(meeting.meeting_id)):
        st.html(
            '<div class="ix-row-top"><span class="ix-row-time">{time}</span>'
            '<p class="ix-row-title">{title}</p>'
            '<span style="margin-left:auto">{chip}</span></div>{meta}{avatars}'.format(
                time=esc(meeting.time_label), title=esc(meeting.title),
                chip=ui.chip(meeting.meeting_type, tone), meta=ui.meta(*bits),
                avatars=ui.avatars(attendee_names(meeting), limit=4))
        )
        row = st.container(key="row-act-m-{}".format(meeting.meeting_id),
                           horizontal=True)
        with row:
            recap = meeting.is_completed
            st.button(
                "Recap" if recap else "Prep",
                key="prep-{}".format(meeting.meeting_id),
                help="Open the {} card".format("recap" if recap else "prep"),
                type="secondary" if recap else "primary",
                on_click=on_meeting, args=(meeting.meeting_id,),
            )
            target = JOIN_TARGETS.get(meeting.location or "")
            if target and not recap and on_join is not None:
                st.button("Join", key="join-{}".format(meeting.meeting_id),
                          help="Open the {} call".format(target),
                          on_click=on_join, args=(target,))


def _actions_column(actions: Sequence[Action], executed_lookup,
                    on_action: Callable[[str], None]) -> None:
    _list_head("Actions", len(actions), "ranked by impact")
    if not actions:
        ui.empty_state("Nothing outstanding.", "You are clear for now.")
        return

    with st.container(key="scroll-actions", height=LIST_HEIGHT, border=False):
        for action in actions:
            _action_row(action, executed_lookup(action.key), on_action)


def _action_row(action: Action, done, on_action) -> None:
    bits = [action.source_display]
    if action.account_name:
        bits.append(action.account_name)
    if action.due_date:
        bits.append(relative_day(action.due_date))
    if action.amount:
        bits.append(money(action.amount))

    safe = action.key.replace(":", "-")
    with st.container(key="lrow-a-{}".format(safe)):
        st.html(
            '<div class="ix-row-top">{dot}<p class="ix-row-title">{t}</p></div>'
            '{m}<p class="ix-row-body">{w}</p>'.format(
                dot=ui.dot("done" if done else action.priority),
                t=esc(action.title), m=ui.meta(*bits),
                w=esc(truncate(action.why, 110)))
        )
        row = st.container(key="row-act-a-{}".format(safe), horizontal=True)
        with row:
            st.button("Open", key="open-{}".format(action.key),
                      help="Open the action card", type="secondary",
                      on_click=on_action, args=(action.key,))
            if done:
                st.html('<span class="ix-chip ix-chip--good" style="margin-top:5px;'
                        'display:inline-block">{}</span>'.format(
                            esc(truncate(done.get("summary", "Done"), 34))))
