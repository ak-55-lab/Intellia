"""Greeting and the ask entry point.

The ask bar sits directly under the greeting rather than in a top chrome bar.
Submitting it opens a conversation, so the canvas is the start of a thread and
not a dead end.
"""

from __future__ import annotations

from datetime import date
from typing import Callable

import streamlit as st

from intellia.config.personas import Persona
from intellia.state import session
from intellia.utils.dates import display_date, greeting_for
from intellia.utils.formatting import esc, first_name

ASK_PLACEHOLDER = "Ask about your pipeline, accounts or day"

SUGGESTIONS = [
    "What should I focus on today?",
    "Which deals are most likely to slip?",
    "Show pipeline by stage",
]


def render_greeting(persona: Persona, as_of: date, scope_label: str) -> None:
    st.html(
        '<div class="ix-greet">'
        '<p class="ix-greet-date">{d}</p>'
        '<h1 class="ix-greet-title">{g}, {n}</h1>'
        '<p class="ix-greet-sub">Here is what deserves your attention today '
        '&middot; {s}</p></div>'.format(
            d=esc(display_date(as_of)), g=esc(greeting_for()),
            n=esc(first_name(persona.label)), s=esc(scope_label))
    )


def render_ask(on_ask: Callable[[str], None], show_suggestions: bool = True) -> None:
    with st.container(key="hero-ask"):
        # st.chat_input nested in a container renders inline rather than
        # bottom-pinned, and brings Enter-to-submit and auto-grow with it.
        #
        # on_submit, NOT the return value. Reading the return value handles the
        # submission halfway down the script, after this view has already begun
        # rendering, so the view switch it triggers is not applied until some
        # later interaction: pressing Enter appeared to do nothing at all. A
        # callback runs before the script body, so the router sees the new view
        # on the very run the submission causes.
        st.chat_input(ASK_PLACEHOLDER, key="ask-input",
                      on_submit=submit_question, args=("ask-input", on_ask))

    if not show_suggestions:
        return
    row = st.container(key="row-suggestions", horizontal=True)
    with row:
        for index, text in enumerate(SUGGESTIONS):
            with st.container(key="sugg-{}".format(index)):
                st.button(text, key="suggbtn-{}".format(index),
                          on_click=on_ask, args=(text,))


def submit_question(state_key: str, on_ask: Callable[[str], None]) -> None:
    """Shared by the hero bar and the thread composer."""
    text = (st.session_state.get(state_key) or "").strip()
    if text:
        on_ask(text)


def page_header(title: str, subtitle: str, back: bool = True) -> None:
    """Header for a secondary view, with the way back to the canvas."""
    row = st.container(key="row-head-page", horizontal=True,
                       vertical_alignment="center")
    with row:
        st.html('<div><h1 class="ix-greet-title" style="font-size:23px;margin:0">{t}</h1>'
                '<p class="ix-greet-sub" style="margin-top:3px">{s}</p></div>'.format(
                    t=esc(title), s=esc(subtitle)))
        if back:
            st.button("My day", key="page-back", icon=":material/today:",
                      on_click=session.go_home)
    st.html('<div style="height:12px"></div>')
