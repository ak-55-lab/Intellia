"""Session state.

Streamlit reruns the whole script on every interaction, so scattering
``st.session_state["..."]`` string keys across twenty components is the single
biggest source of bugs in an app this size. One module owns the key namespace;
components read state but mutate it only through the named setters here.

Three pieces of routing live here:

* ``view``        which screen the shell is showing (my day, chat, settings, ...).
* ``threads``     the conversation history the left rail lists.
* ``open_dialog`` the intent ONE dispatcher in ``app.py`` reads. Components never
  open a dialog themselves, because Streamlit permits exactly one per script run.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

from intellia.config.personas import DEFAULT_PERSONA

HOME = "my_day"

VIEWS = ("my_day", "chat", "projects", "skills", "digests", "apps",
         "updates", "settings")

DEFAULTS: Dict[str, Any] = {
    "persona_id": DEFAULT_PERSONA,
    "view": HOME,
    "open_dialog": None,        # (kind, entity_id), read by ONE dispatcher in app.py
    "pulse_band": None,
    "threads": None,            # [{id, title, turns: [{q, answer}]}]
    "thread_id": None,
    "nav_query": "",
    "executed_actions": None,
    "widget_filters": None,
    "edit_candidate": None,
    "compose_tab": None,
    "created_notice": None,
    "pending_question": None,
    "pending_state": None,
    "editing_block": None,
    "preview_cache": None,
}

_LISTS = ("threads",)
_DICTS = ("executed_actions", "widget_filters", "preview_cache")


def init() -> None:
    for key, value in DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = ([] if key in _LISTS
                                     else {} if key in _DICTS else value)


# -- persona ---------------------------------------------------------------------------

def persona_id() -> str:
    return st.session_state.get("persona_id", DEFAULT_PERSONA)


def set_persona(value: str) -> None:
    if value != st.session_state.get("persona_id"):
        st.session_state["persona_id"] = value
        # Persona changes every band's data; clear anything persona-specific.
        st.session_state["open_dialog"] = None
        st.session_state["widget_filters"] = {}


# -- view routing ----------------------------------------------------------------------

def view() -> str:
    current = st.session_state.get("view", HOME)
    return current if current in VIEWS else HOME


def set_view(value: str) -> None:
    st.session_state["view"] = value if value in VIEWS else HOME
    st.session_state["open_dialog"] = None
    st.session_state["editing_block"] = None


def go_home() -> None:
    """New chat lands on My Day: the canvas is where a conversation starts."""
    st.session_state["thread_id"] = None
    set_view(HOME)


# -- conversation ----------------------------------------------------------------------

def threads() -> List[Dict[str, Any]]:
    return st.session_state.get("threads") or []


def thread_id() -> Optional[str]:
    return st.session_state.get("thread_id")


def current_thread() -> Optional[Dict[str, Any]]:
    active = thread_id()
    return next((t for t in threads() if t["id"] == active), None) if active else None


def open_thread(value: str) -> None:
    st.session_state["thread_id"] = value
    set_view("chat")
    st.session_state["thread_id"] = value      # set_view must not clear the target


def start_thread(question: str) -> str:
    """Create a thread and queue the question. The view renders it, then answers."""
    new_id = "th-" + uuid.uuid4().hex[:10]
    st.session_state.setdefault("threads", [])
    st.session_state["threads"].insert(
        0, {"id": new_id, "title": question.strip()[:52], "turns": []})
    st.session_state["thread_id"] = new_id
    st.session_state["view"] = "chat"
    st.session_state["pending_question"] = question
    st.session_state["pending_state"] = "queued"
    return new_id


def queue_question(question: str) -> None:
    st.session_state["pending_question"] = question
    st.session_state["pending_state"] = "queued"


def pending_question() -> Optional[str]:
    return st.session_state.get("pending_question")


def pending_is_queued() -> bool:
    """True until the answer run starts.

    The two states are what let the view paint the question first and answer on a
    later, fragment-scoped run, instead of holding the whole page while the model
    thinks.
    """
    return (st.session_state.get("pending_question") is not None
            and st.session_state.get("pending_state") == "queued")


def mark_pending_running() -> None:
    st.session_state["pending_state"] = "running"


def clear_pending_question() -> None:
    st.session_state["pending_question"] = None
    st.session_state["pending_state"] = None


def append_turn(question: str, answer: Any) -> None:
    thread = current_thread()
    if thread is None:
        start_thread(question)
        thread = current_thread()
    if thread is not None:
        thread["turns"].append({"q": question, "a": answer})


def nav_query() -> str:
    return st.session_state.get("nav_query", "") or ""


# -- answer chart cache ----------------------------------------------------------------
# Keyed by SQL, so replaying a thread does not re-run every turn's query on every
# rerun. It lives in session state, not the LLM cache: these are results, and the
# query that produced them is already saved on the turn.

def cache_preview(question: str, rendered: Any, chart: Any) -> None:
    store = st.session_state.setdefault("preview_cache", {})
    sql = getattr(getattr(rendered, "config", None), "generated_sql", "") or question
    store[sql] = (rendered, chart)


def cached_preview(sql: str) -> Optional[Tuple[Any, Any]]:
    return st.session_state.get("preview_cache", {}).get(sql)


# -- dialogs ---------------------------------------------------------------------------

def open_dialog() -> Optional[Tuple[str, str]]:
    return st.session_state.get("open_dialog")


def set_dialog(kind: str, entity_id: str = "") -> None:
    st.session_state["open_dialog"] = (kind, entity_id)


def clear_dialog() -> None:
    st.session_state["open_dialog"] = None
    st.session_state["edit_candidate"] = None


# -- band highlight --------------------------------------------------------------------

def pulse(band: str) -> None:
    st.session_state["pulse_band"] = band


def take_pulse() -> Optional[str]:
    value = st.session_state.get("pulse_band")
    st.session_state["pulse_band"] = None
    return value


# -- compose ---------------------------------------------------------------------------

def editing_block() -> Optional[str]:
    return st.session_state.get("editing_block")


def toggle_block_editor(block_id: str) -> None:
    current = st.session_state.get("editing_block")
    st.session_state["editing_block"] = None if current == block_id else block_id


def compose_tab() -> Optional[str]:
    return st.session_state.get("compose_tab")


def set_compose_tab(value: Optional[str]) -> None:
    current = st.session_state.get("compose_tab")
    st.session_state["compose_tab"] = None if current == value else value


# -- actions ---------------------------------------------------------------------------

def executed(action_key: str) -> Optional[Dict[str, Any]]:
    return st.session_state.get("executed_actions", {}).get(action_key)


def mark_executed(action_key: str, record: Dict[str, Any]) -> None:
    st.session_state.setdefault("executed_actions", {})[action_key] = record


# -- widget filters --------------------------------------------------------------------

def widget_filter(widget_key: str) -> Dict[str, Any]:
    return st.session_state.get("widget_filters", {}).get(widget_key, {})


def set_widget_filter(widget_key: str, value: Dict[str, Any]) -> None:
    st.session_state.setdefault("widget_filters", {})[widget_key] = value


# -- edit candidate --------------------------------------------------------------------

def set_edit_candidate(payload: Any) -> None:
    st.session_state["edit_candidate"] = payload


def edit_candidate() -> Any:
    return st.session_state.get("edit_candidate")


# -- notices ---------------------------------------------------------------------------

def set_notice(text: str) -> None:
    st.session_state["created_notice"] = text


def take_notice() -> Optional[str]:
    value = st.session_state.get("created_notice")
    st.session_state["created_notice"] = None
    return value


def last_answered_turn() -> Optional[Dict[str, Any]]:
    """The most recent turn in this thread that produced a query.

    A follow-up like "flip this to a donut" only means something relative to the
    turn before it, and the generator is otherwise handed one bare sentence.
    Turns that answered from the evidence bundle alone carry no SQL to build on,
    so they are skipped rather than returned empty.
    """
    thread = current_thread()
    if thread is None:
        return None
    for turn in reversed(thread.get("turns") or []):
        insight = getattr(turn.get("a"), "insight", None)
        if insight is not None and getattr(insight, "sql", ""):
            return {"question": turn.get("q", ""), "sql": insight.sql,
                    "viz": getattr(insight, "visualization", "") or "table"}
    return None


# -- per-chat question budget ----------------------------------------------------------
# A conversation is capped so a thread cannot grow without bound. The remedy is a
# real control the reader already has: New chat, in the rail. Counting every
# question rather than only the ones that reach the model keeps the number the
# banner shows equal to the number the reader counted themselves.

MAX_QUESTIONS_PER_THREAD = 5


def questions_used(thread: Optional[Dict[str, Any]] = None) -> int:
    """Answered turns in this thread, plus one for a question already in flight."""
    thread = thread if thread is not None else current_thread()
    if thread is None:
        return 0
    used = len(thread.get("turns") or [])
    if pending_question() is not None and thread_id() == thread.get("id"):
        used += 1
    return used


def questions_left(thread: Optional[Dict[str, Any]] = None) -> int:
    return max(0, MAX_QUESTIONS_PER_THREAD - questions_used(thread))


def thread_is_full(thread: Optional[Dict[str, Any]] = None) -> bool:
    return questions_left(thread) <= 0
