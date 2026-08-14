"""The conversation view.

One thread per question asked from the canvas. Answers come from the live model
when a key is present and from the deterministic builder when it is not, but the
grounding is identical either way: the evidence bundle and the already-computed
metrics go in, prose comes back, and no number is ever authored by the model.

The question and the answer are painted in two different runs, on purpose. See
``render_thread`` for why: doing both in one run leaves the whole previous page
on screen, greyed out, for as long as the model takes.
"""

from __future__ import annotations

from typing import Any, Callable, Dict

import streamlit as st

from intellia.components import primitives as ui
from intellia.state import session
from intellia.theme import brand
from intellia.utils.formatting import esc, truncate


def render_thread(thread: Dict[str, Any], ai_mode: str,
                  answer_fn: Callable[[str], Any],
                  preview_fn: Callable[[Any], Any],
                  on_ask: Callable[[str], None],
                  on_pin: Callable[[Any, str], None]) -> None:
    # A single wrapper container, not a raw div: st.html sanitises and closes each
    # fragment independently, so an unbalanced opening tag would never wrap anything.
    with st.container(key="thread-body"):
        total = len(thread["turns"])
        for index, turn in enumerate(thread["turns"]):
            _turn(turn["q"], turn["a"], index, ai_mode, preview_fn, on_ask, on_pin,
                  last=(index == total - 1))

        pending = session.pending_question()
        if not pending:
            if session.thread_is_full():
                _limit_reached()
            return

        # The question paints in the run that switches view; the answer is
        # computed in a LATER, fragment-scoped run.
        #
        # Doing both in one run is what caused the whole previous page to sit on
        # screen greyed out for the length of the model call: Streamlit only
        # clears the elements of the old page when the run that replaces them
        # finishes. Splitting it means run one ends immediately (old page gone,
        # question and skeleton up), and the timer wakes a fragment that does the
        # work without touching anything else on screen.
        _question(pending)
        st.fragment(
            lambda: _resolve(pending, total, ai_mode, answer_fn, preview_fn,
                             on_ask, on_pin),
            run_every=0.25 if session.pending_is_queued() else None,
        )()


def _resolve(question: str, index: int, ai_mode: str, answer_fn, preview_fn,
             on_ask, on_pin) -> None:
    """The thinking indicator on the first paint, the model call on the rerun."""
    if session.pending_is_queued():
        session.mark_pending_running()
        _thinking()
        return

    answer = answer_fn(question)
    session.append_turn(question, answer)
    session.clear_pending_question()
    # Back to a normal run: this drops the timer and re-renders the thread with
    # the new turn in it.
    st.rerun()


def _turn(question: str, answer: Any, index: int, ai_mode: str, preview_fn,
          on_ask, on_pin, last: bool) -> None:
    _question(question)
    _answer(answer, index, ai_mode, preview_fn, on_ask, on_pin, last)


def _limit_reached() -> None:
    """Closing note on a full chat, with the way out beside it.

    The rail already has New chat; repeating it here means the reader does not
    have to go looking for the remedy the message just named.
    """
    with st.container(key="thread-limit"):
        st.html(
            '<p class="ix-limit-title">{}</p>'
            '<p class="ix-limit-body">{}</p>'.format(
                esc("You have reached {} questions in this chat.".format(
                    session.MAX_QUESTIONS_PER_THREAD)),
                esc("Start a new chat to keep going. This one stays in your rail, "
                    "and anything you pinned stays on the canvas.")))
        st.button("New chat", key="limit-new-chat", on_click=session.go_home,
                  type="primary")


def _question(text: str) -> None:
    st.html('<div class="ix-msg-user">{}</div>'.format(esc(text)))


def _thinking() -> None:
    """The mark, pulsing, while the model works.

    A skeleton implies layout that is about to appear at that size, which is not
    what is happening here: the answer is being written. The mark is the same one
    that labels every answer, so the wait reads as Intellia thinking rather than
    as the page still loading.
    """
    st.html(
        '<div class="ix-msg-ai ix-thinking">{m}'
        '<span class="ix-thinking-text">Thinking</span>'
        '<span class="ix-dots"><i></i><i></i><i></i></span></div>'.format(
            m=brand.mark(15))
    )


def _answer(answer: Any, index: int, ai_mode: str, preview_fn,
            on_ask, on_pin, last: bool) -> None:
    if answer is None:
        ui.error_card("I could not answer that one.",
                      "Try asking about pipeline, deals, meetings or signals.")
        return

    st.html('<div class="ix-msg-ai">{m}{t}</div>'.format(
        m=brand.mark(15), t=esc(answer.text).replace("\n", "<br>")))

    insight = getattr(answer, "insight", None)
    if insight is not None and insight.sql:
        _preview(insight, index, preview_fn, on_pin)

    st.html('<p class="ix-msg-note">{}</p>'.format(
        esc("Answered from your data by {}".format(
            getattr(answer, "generated_by", None) or ai_mode))))

    # Suggested follow-ups are hidden once the chat is full: offering a question
    # the composer will refuse reads as a broken button.
    if last and getattr(answer, "follow_ups", None) and not session.thread_is_full():
        row = st.container(key="row-followups-{}".format(index), horizontal=True)
        with row:
            for number, text in enumerate(answer.follow_ups[:3]):
                with st.container(key="sugg-f{}-{}".format(index, number)):
                    st.button(truncate(text, 46), key="fu-{}-{}".format(index, number),
                              on_click=on_ask, args=(text,))


def _preview(insight: Any, index: int, preview_fn, on_pin) -> None:
    """Show the chart the question implies, with one click to keep it."""
    try:
        rendered, chart = preview_fn(insight)
    except Exception:
        return
    if rendered is None or not rendered.ok:
        return

    # An empty result keeps its card. Returning early hid the title and the query
    # too, so a question whose honest answer is "none" looked the same as one the
    # app had failed to understand.
    empty = rendered.frame.empty

    with ui.card("preview-{}".format(index)):
        head = st.container(key="row-head-preview-{}".format(index), horizontal=True,
                            vertical_alignment="center")
        with head:
            st.html(ui.card_header(insight.title or "Result", insight.description))
            st.button("Pin to canvas", key="pin-{}".format(index),
                      icon=":material/push_pin:", type="primary",
                      on_click=on_pin, args=(insight, ""))
        if empty:
            ui.empty_state("Nothing matched.",
                           "The query ran against your data and returned no rows.")
        elif chart is not None:
            st.altair_chart(chart, use_container_width=True, theme=None)
        else:
            st.dataframe(rendered.frame.head(8), hide_index=True, width="stretch")
        st.html(ui.card_footer("Generated for this question"))
