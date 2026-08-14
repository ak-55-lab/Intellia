"""End-to-end UI smoke tests via Streamlit's own AppTest harness.

These run the real ``app.py`` script, so they catch the class of bug unit tests
miss entirely: illegal Streamlit API use (nested dialogs, fragment-scoped reruns
on first paint, unsupported kwargs) and broken routing between views.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from streamlit.testing.v1 import AppTest  # noqa: E402


def _app() -> AppTest:
    os.environ["ANTHROPIC_API_KEY"] = ""     # deterministic mode for the whole file
    app = AppTest.from_file(str(APP_DIR / "app.py"), default_timeout=180)
    app.run()
    return app


def _keys(app: AppTest, prefix: str):
    return [b.key for b in app.button if b.key.startswith(prefix)]


def _click(app: AppTest, key: str) -> AppTest:
    matches = [b for b in app.button if b.key == key]
    assert matches, "no button keyed {}".format(key)
    matches[0].click().run()
    assert not app.exception, [str(e.value)[:200] for e in app.exception]
    return app


@pytest.fixture(scope="module")
def app() -> AppTest:
    return _app()


def test_app_renders_without_exceptions(app):
    assert not app.exception, [str(e.value)[:200] for e in app.exception]


def test_canvas_has_its_bands(app):
    assert len(app.button) > 10               # nav, meetings, actions, menus
    assert app.session_state["view"] == "my_day"
    assert _keys(app, "prep-"), "no meeting rows rendered"
    assert _keys(app, "open-"), "no action rows rendered"


def test_left_rail_reaches_every_view():
    app = _app()
    for view in ("projects", "skills", "digests", "apps"):
        _click(app, "navbtn-{}".format(view))
        assert app.session_state["view"] == view
    _click(app, "nav-updates")                # product updates has its own entry
    assert app.session_state["view"] == "updates"
    _click(app, "navbtn-profile")
    assert app.session_state["view"] == "settings"
    # New chat is the way back to the canvas, per the navigation model.
    _click(app, "navbtn-my_day")
    assert app.session_state["view"] == "my_day"


def test_persona_switch_rerenders_cleanly():
    app = _app()
    _click(app, "navbtn-profile")             # the switcher lives in settings
    _click(app, "persona-manager")
    assert app.session_state["persona_id"] == "manager"


def test_meeting_prep_opens_a_dialog_not_an_inline_panel():
    """Prep opens as a medium card over the canvas, via the one dispatcher."""
    app = _app()
    prep = _keys(app, "prep-")
    assert prep, "no meeting rows rendered"
    _click(app, prep[0])
    kind, entity = app.session_state["open_dialog"]
    assert kind == "meeting" and entity


def test_action_detail_opens_a_dialog():
    app = _app()
    opens = _keys(app, "open-")
    assert opens, "no action rows rendered"
    _click(app, opens[0])
    assert app.session_state["open_dialog"][0] == "action"


def test_card_controls_reach_the_dispatcher_from_outside_the_fragment():
    """Regression: the control strip used to live inside the card's fragment.

    A click in there reruns only the fragment, so the dialog intent was set and
    the dispatcher in app.py never ran: edit with AI silently did nothing. The
    strip renders outside the fragment now, and this asserts the intent lands.
    """
    app = _app()
    strips = sorted({b.key for b in app.button if b.key.startswith("ctl-insight-")})
    assert strips, "no insight control strips rendered"
    stem = strips[0].rsplit("-", 1)[0]           # ctl-insight-<id>
    widget_key = stem[len("ctl-"):].replace("-", ".", 1)

    _click(app, "{}-0".format(stem))             # edit with AI
    assert app.session_state["open_dialog"] == ("edit", widget_key)


def test_card_controls_toggle_table_resize_reorder_and_remove():
    app = _app()
    strips = sorted({b.key for b in app.button if b.key.startswith("ctl-insight-")})
    stem = strips[0].rsplit("-", 1)[0]
    widget_key = stem[len("ctl-"):].replace("-", ".", 1)

    _click(app, "{}-1".format(stem))             # chart to table
    assert app.session_state["widget_filters"][widget_key]["as_table"] is True
    _click(app, "{}-1".format(stem))
    assert app.session_state["widget_filters"][widget_key]["as_table"] is False

    _click(app, "{}-2".format(stem))             # width
    _click(app, "{}-4".format(stem))             # move down
    _click(app, "{}-3".format(stem))             # move back up
    assert not app.exception, [str(e.value)[:200] for e in app.exception]

    before = len([b for b in app.button if b.key.startswith("ctl-insight-")])
    _click(app, "{}-5".format(stem))             # remove from canvas
    after = len([b for b in app.button if b.key.startswith("ctl-insight-")])
    assert after < before, "remove should take the card off the canvas"

    # Restore, so the suite stays re-runnable.
    _click(app, "toolbtn-insights")
    _click(app, "vis-{}".format(widget_key.replace(".", "-")))


def test_user_can_add_a_heading_block_and_edit_it():
    """Section titles and notes are widgets, so they get the same controls."""
    app = _app()
    _click(app, "toolbtn-layout")
    _click(app, "add-heading")
    block_id = app.session_state["editing_block"]
    assert block_id and block_id.startswith("block.")

    safe = block_id.replace(".", "-")
    field = "block-title-{}".format(safe)
    matches = [i for i in app.text_input if i.key == field]
    assert matches, "the new block should open its editor"
    matches[0].set_value("Pipeline health").run()
    # The edit control both saves and closes the editor.
    _click(app, "ctl-{}-0".format(safe))
    assert app.session_state["editing_block"] is None


def test_composer_toggles_a_widget_off_the_canvas():
    """Layout visibility persists in app_state.db by design, so the starting state
    varies between runs: establish it explicitly rather than assuming it."""
    app = _app()
    _click(app, "toolbtn-insights")           # reveal the insight tiles
    tiles = [k for k in _keys(app, "vis-insight-")]
    assert tiles, "no insight tiles in the composer"
    key = tiles[0]

    def controls() -> int:
        return len(app.dataframe) + len(app.button)

    _click(app, key)
    first = controls()
    _click(app, key)                          # back to where it started
    second = controls()
    assert first != second, "toggling a tile should change what is on the canvas"


def test_composer_create_opens_the_ai_dialog():
    app = _app()
    _click(app, "composer-create")
    assert app.session_state["open_dialog"][0] == "create"


def test_asking_a_question_routes_to_chat_before_answering():
    """The switch must not wait on the model.

    Answering in the same run leaves the whole previous page on screen, greyed
    out, for as long as the call takes. The question is queued and painted first;
    a timed fragment does the work on a later run.
    """
    app = _app()
    _click(app, "suggbtn-0")
    assert app.session_state["view"] == "chat"
    assert app.session_state["pending_question"]
    # The first run paints the question and a skeleton and hands off; the answer
    # arrives on the timed fragment rerun that follows.
    assert app.session_state["pending_state"] == "running"

    threads = app.session_state["threads"]
    assert len(threads) == 1
    assert threads[0]["turns"] == [], "the answer belongs to the next run"
    # The thread is already listed in the rail and reachable again.
    assert _keys(app, "histbtn-")


def test_the_hero_ask_bar_actually_submits():
    """Regression: the hero bar read chat_input's return value.

    That handles the submission part way down the script, after My Day has begun
    rendering, so the view switch it triggers is not applied until some later
    interaction. Pressing Enter appeared to do nothing at all.
    """
    app = _app()
    assert app.chat_input, "no ask bar rendered"
    app.chat_input[0].set_value("What is my open pipeline?").run()
    assert not app.exception, [str(e.value)[:200] for e in app.exception]
    assert app.session_state["view"] == "chat"
    assert app.session_state["threads"][0]["title"] == "What is my open pipeline?"


def test_a_full_chat_stops_accepting_questions():
    """The cap has to hold at the composer, not just in the counter.

    Five answered turns are seeded directly: driving five real turns through the
    fragment and its timer would test Streamlit's scheduler rather than the cap.
    """
    app = _app()
    app.chat_input[0].set_value("What is my open pipeline?").run()
    thread_id = app.session_state["thread_id"]

    thread = next(t for t in app.session_state["threads"] if t["id"] == thread_id)
    thread["turns"] = [{"q": "q{}".format(i), "a": None} for i in range(5)]
    app.session_state["pending_question"] = None
    app.session_state["pending_state"] = None
    app.run()
    assert not app.exception, [str(e.value)[:200] for e in app.exception]

    composer = [c for c in app.chat_input if c.key == "thread-input"]
    assert composer, "the thread composer disappeared instead of disabling"
    assert composer[0].disabled, "a full chat still accepts a sixth question"
    assert _keys(app, "limit-new-chat"), "no way out of a full chat was offered"


def test_a_new_chat_starts_with_a_full_budget():
    """The way out has to actually work, or the limit is a dead end."""
    from intellia.state import session as session_state

    app = _app()
    app.chat_input[0].set_value("What is my open pipeline?").run()
    thread = next(t for t in app.session_state["threads"]
                  if t["id"] == app.session_state["thread_id"])
    thread["turns"] = [{"q": "q{}".format(i), "a": None} for i in range(5)]
    app.session_state["pending_question"] = None
    app.session_state["pending_state"] = None
    app.run()

    _click(app, "limit-new-chat")
    assert not app.exception, [str(e.value)[:200] for e in app.exception]
    assert app.session_state["thread_id"] is None, "still pinned to the full chat"
    assert app.session_state["view"] == session_state.HOME


def test_an_empty_canvas_shows_one_message_not_a_section_shell():
    """Removing the last widget left an "Insights" header over an empty-state card.

    A titled section wrapping nothing reads as a band that failed to load rather
    than as a canvas the reader deliberately cleared.

    Blocks are cleared as well as widgets: an earlier test leaves a heading behind,
    and a heading is a canvas item, so leaving it makes the band correct to draw.
    """
    from intellia.bootstrap import build_context

    ctx = build_context()
    persona = "rep"
    for widget in ctx.registry.for_persona(persona):
        ctx.store.set_visibility(persona, widget.key, False)
    for key in ("component.meetings", "component.actions"):
        ctx.store.set_visibility(persona, key, False)
    for block in ctx.store.blocks(persona):
        ctx.store.delete_block(block["id"])

    app = _app()
    assert not app.exception, [str(e.value)[:200] for e in app.exception]

    painted = " ".join(h.body for h in app.get("html") if getattr(h, "body", None))
    assert "Your canvas is empty" in painted, "no canvas-level empty state"
    assert "band-insights" not in painted, "Insights band drawn over an empty canvas"
