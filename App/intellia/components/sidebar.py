"""The left rail.

Fixed dark navy in both themes, because it is chrome rather than canvas. Every
row is a real button so navigation is a callback, not a link, and the active
row is marked by container key (``nav-on-*``) rather than by an inline style,
which keeps the skin in the stylesheet where the rest of the system lives.
"""

from __future__ import annotations

from typing import Callable

import streamlit as st

from intellia.config.personas import Persona
from intellia.state import session
from intellia.theme import brand
from intellia.utils.formatting import esc, truncate

NAV_ITEMS = [
    ("my_day", "New chat", ":material/add:", "Start fresh on your daily canvas"),
    ("projects", "Portfolio", ":material/folder_open:", "Every account in your book"),
    ("skills", "Skills", ":material/bolt:", "What Intellia can do on your behalf"),
    ("digests", "Digests", ":material/summarize:", "Scheduled briefings and alerts"),
    ("apps", "Apps", ":material/apps:", "Connected systems and permissions"),
]

SUPPORT_TEAM = "RevOps"

# One line each in the rail. The detail lives on the updates page; repeating it
# here just pushed the profile up the screen.
PRODUCT_UPDATES = [
    ("Insight versioning", "New"),
    ("Faster answers", "New"),
    ("Navy chart system", "Updated"),
]


def render(persona: Persona, ai_mode: str, on_ask: Callable[[str], None]) -> None:
    with st.sidebar:
        st.html(brand.wordmark("beta"))
        _nav()
        _search_and_history(on_ask)
        # Everything from here down is pinned to the bottom edge of the rail by
        # `margin-top: auto` on this group, so the chat list gets all the slack
        # however long it grows. An empty spacer container would not work:
        # Streamlit does not render a container with nothing in it.
        with st.container(key="nav-bottom"):
            _updates()
            _profile(persona, ai_mode)
            _support()


# -- navigation --------------------------------------------------------------------------

def _nav() -> None:
    current = session.view()
    for view, label, icon, hint in NAV_ITEMS:
        active = current == view and not (view == "my_day" and session.thread_id())
        key = "nav-on-{}".format(view) if active else "nav-{}".format(view)
        with st.container(key=key):
            st.button(
                label, key="navbtn-{}".format(view), icon=icon, help=hint,
                width="stretch",
                type="primary" if view == "my_day" else "secondary",
                on_click=session.go_home if view == "my_day" else session.set_view,
                args=() if view == "my_day" else (view,),
            )


# -- search and chat history ---------------------------------------------------------------

def _search_and_history(on_ask: Callable[[str], None]) -> None:
    st.html('<p class="ix-nav-label">Search</p>')
    query = st.text_input(
        "Search", key="nav_query", placeholder="Search chats or ask",
        label_visibility="collapsed",
    )
    lowered = (query or "").strip().lower()

    threads = session.threads()
    matches = [t for t in threads
               if not lowered or lowered in t["title"].lower()
               or any(lowered in turn["q"].lower() for turn in t["turns"])]

    if lowered and not matches:
        st.button("Ask: {}".format(truncate(query, 24)), key="nav-ask-new",
                  icon=":material/auto_awesome:", width="stretch",
                  on_click=on_ask, args=(query,))

    st.html('<p class="ix-nav-label">Chats</p>')
    if not threads:
        st.html('<p class="ix-nav-empty">No conversations yet. Ask something from '
                'your canvas.</p>')
        return

    active = session.thread_id()
    for thread in matches[:8]:
        key = ("nav-on-hist-{}" if thread["id"] == active else "hist-{}").format(thread["id"])
        with st.container(key=key):
            st.button(truncate(thread["title"], 30), key="histbtn-{}".format(thread["id"]),
                      icon=":material/forum:", width="stretch",
                      on_click=session.open_thread, args=(thread["id"],))
    if len(matches) > 8:
        st.html('<p class="ix-nav-note">{} more not shown</p>'.format(len(matches) - 8))


# -- product updates -----------------------------------------------------------------------

def _updates() -> None:
    rows = "".join(
        '<div class="ix-nav-update"><b>{t}</b><i>{tag}</i></div>'.format(
            t=esc(title), tag=esc(tag))
        for title, tag in PRODUCT_UPDATES[:3])
    st.html('<p class="ix-nav-label">Product updates</p>{}'.format(rows))
    with st.container(key="nav-updates-link"):
        st.button("See all", key="nav-updates", icon=":material/north_east:",
                  on_click=session.set_view, args=("updates",))


# -- profile -------------------------------------------------------------------------------

def _profile(persona: Persona, ai_mode: str) -> None:
    with st.container(key="nav-profile"):
        st.button(
            persona.label, key="navbtn-profile", icon=":material/account_circle:",
            width="stretch",
            help="Profile and settings. Assistant: {}".format(ai_mode),
            # ai_mode is the flagship tier; Settings lists both, because
            # interactive work runs on the fast one.
            on_click=session.set_view, args=("settings",),
        )
        st.html('<p class="ix-nav-note">{r} &middot; {s}</p>'.format(
            r=esc(persona.role_label), s=esc(persona.scope_label)))


def _support() -> None:
    with st.container(key="nav-support"):
        st.html(
            '<p class="ix-nav-support">Questions or need help?<br>'
            '<span>Reach out to {} for support.</span></p>'.format(esc(SUPPORT_TEAM)))
