"""Intellia.

Composition only. Every band delegates to a component; every component takes
already-built domain objects. The two pieces of real logic here are the view
router and the dialog dispatcher at the bottom, which exists because Streamlit
permits exactly one dialog per script run.

Run from this directory so Streamlit picks up .streamlit/config.toml:

    python3 -m streamlit run app.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import streamlit as st  # noqa: E402

st.set_page_config(
    page_title="Intellia",
    page_icon=str(APP_DIR / "intellia" / "assets" / "logo.svg"),
    layout="wide",
    initial_sidebar_state="expanded",
)

from intellia.actions.playbooks import render_template, sample_message  # noqa: E402
from intellia.ai.prompts import knowledge, tasks  # noqa: E402
from intellia.bootstrap import build_context, refresh_insight_widgets  # noqa: E402
from intellia.components import (  # noqa: E402
    chat, chrome, composer, dialogs, insights, panels, sidebar, views,
)
from intellia.components import primitives as ui  # noqa: E402
from intellia.models.ai import ActionExplanation  # noqa: E402
from intellia.services.ask_service import (  # noqa: E402
    AskService, frame_to_markdown, wants_insight,
)
from intellia.state import session  # noqa: E402
from intellia.theme import brand, charts, tokens  # noqa: E402
from intellia.utils.dates import refreshed_label, relative_day  # noqa: E402
from intellia.utils.formatting import esc, money, truncate  # noqa: E402
from intellia.utils.logging import get_logger  # noqa: E402

log = get_logger("app")


# ======================================================================================
# one-time setup
# ======================================================================================

@st.cache_resource(show_spinner=False)
def _context() -> Any:
    return build_context()


@st.cache_resource(show_spinner=False)
def _ask_service(_ctx: Any) -> AskService:
    return AskService(_ctx.ai, _ctx.context, _ctx.metrics)


@st.cache_data(show_spinner=False)
def _stylesheet(dark: bool) -> str:
    """Tokens plus stylesheet as one inline style block.

    Passing a Path to st.html is documented to wrap a .css file automatically, but
    on this Streamlit build nothing reached the DOM (verified: no style tag
    contained our rules), so the file is read and injected explicitly.

    ``dark`` is the same flag the charts get, so the palette can never disagree
    with the widget theme (see tokens.root_css for why this is not a media query).
    """
    css = (APP_DIR / "intellia" / "assets" / "intellia.css").read_text(encoding="utf-8")
    return "<style>{}\n{}\n{}</style>".format(
        tokens.root_css(dark), brand.mark_css(), css)


def _load_styles(dark: bool) -> None:
    st.html(_stylesheet(dark))


def _is_dark() -> bool:
    try:
        return getattr(st.context, "theme", None) is not None and \
            getattr(st.context.theme, "type", "light") == "dark"
    except Exception:
        return False


# ======================================================================================
# helpers
# ======================================================================================

# Tiles to a row in the stat band. Held constant so the row keeps its rhythm as
# the user adds and removes stat cards.
STAT_COLUMNS = 3


def _attendee_names(ctx: Any, scope: Any):
    def resolve(meeting) -> List[str]:
        names: List[str] = []
        for uid in meeting.attendee_user_ids:
            user = ctx.users.get(uid)
            if user:
                names.append(user.full_name)
        if meeting.attendee_contact_ids:
            for contact in ctx.contacts.get_many(scope, meeting.attendee_contact_ids):
                names.append(contact.full_name)
        return names
    return resolve


def _visibility(ctx: Any, persona_id: str, widgets) -> Dict[str, bool]:
    stored = ctx.store.layout(persona_id)
    return {w.key: stored.get(w.key, w.key in ctx.persona(persona_id).default_widgets)
            for w in widgets}


def _band_pulse() -> None:
    band = session.take_pulse()
    if not band:
        return
    # JS cannot reach the parent DOM from st.html, so the highlight is emitted as a
    # one-shot style block rather than triggered by script.
    st.html(
        "<style>.st-key-band-{b} {{ animation: ix-pulse 1.2s ease-out 1; }}</style>"
        .format(b=esc(band))
    )


# ======================================================================================
# provenance shown by the info panel on every widget
# ======================================================================================

# Both panels below carry the same rows in the same order. A stat tile the user
# created and a built-in one sit side by side in the stat band, so a reader who
# opens one definition and then the other must not have to re-learn the layout.
# Only the version row is extra, because only a saved insight has versions.

def _kpi_info(metric: Any, scope: Any) -> List[Tuple[str, str]]:
    return [
        ("Definition", " ".join(p for p in (metric.label, metric.caption) if p)),
        ("Calculation", metric.calculation),
        ("Data source", "Intellia CRM (SQLite)"),
        ("Scope", scope.label),
        ("Last refreshed", refreshed_label()),
        ("Refresh cadence", "Hourly"),
        ("Widget type", "Built in"),
    ]


def _panel_info(definition: str, source: str, widget_type: str,
                generated_by: str) -> List[Tuple[str, str]]:
    return [
        ("Definition", definition),
        ("Data source", source),
        ("Last refreshed", refreshed_label()),
        ("Widget type", widget_type),
        ("Generated by", generated_by),
    ]


def _insight_info(config: Any, scope: Any) -> List[Tuple[str, str]]:
    return [
        # The full description lives here, which is why the card subtitle is free
        # to be one short line.
        ("Definition", config.description or config.subtitle),
        ("Calculation", config.metadata.calculation or "See the query below."),
        ("Data source", config.metadata.data_source),
        ("Scope", scope.label),
        ("Last refreshed", refreshed_label()),
        ("Refresh cadence", config.refresh.cadence_label),
        ("Widget type", "Built in" if config.metadata.source == "builtin"
         else "Created with AI"),
        ("Version", "v{}".format(config.version)),
    ]


# ======================================================================================
# bands
# ======================================================================================
#
# Every card carries the same control strip, built here so one widget cannot end
# up with a different set of controls than its neighbour. Streamlit has no
# drag-and-drop, so ordering is arrows and width is a toggle, both persisted per
# persona in the layout table.

def _controls(ctx: Any, persona_id: str, key: str, order: List[str],
              editable: bool = False, resizable: bool = True,
              table_toggle: bool = True) -> List[Any]:
    controls: List[Any] = []
    if editable:
        controls.append((":material/auto_awesome:", "Edit with AI",
                         session.set_dialog, ("edit", key)))
        # A stat tile has one number and no chart to swap for, so it takes the
        # same controls a built-in KPI takes.
        if table_toggle:
            controls.append((":material/table_rows:", "Switch chart and table",
                             _toggle_table, (key,)))
    if resizable:
        controls.append((":material/width_normal:", "Half width or full width",
                         _cycle_span, (ctx, persona_id, key)))
    controls.append((":material/arrow_upward:", "Move up",
                     _move_widget, (ctx, persona_id, key, order, -1)))
    controls.append((":material/arrow_downward:", "Move down",
                     _move_widget, (ctx, persona_id, key, order, 1)))
    controls.append((":material/close:", "Remove from canvas",
                     _hide_widget, (ctx, key)))
    return controls


def _is_stat(ctx: Any, key: str) -> bool:
    """Does this widget belong in the stat band?

    A built-in KPI and a created insight that resolves to a single number are the
    same thing to a reader, so they share the band, the tile and the controls.
    Testing the saved viz type rather than a ``kpi.`` key prefix is what lets a
    card the user created sit beside Open pipeline instead of half width down
    among the charts.
    """
    spec = ctx.registry.get(key)
    if spec is None:
        return False
    return spec.kind == "kpi" or (spec.kind == "insight" and spec.viz_type == "metric")


def _render_stats(ctx: Any, persona: Any, scope: Any, visibility: Dict[str, bool],
                  dark: bool) -> None:
    keys = [k for k in _ordered(ctx, persona, ("insights",), visibility)
            if _is_stat(ctx, k)]
    if not keys:
        return
    # Fixed three to a row, padded, so tiles keep one width however many there
    # are. Sizing the columns to the count instead makes every tile shrink the
    # moment a fourth is added, which is a layout that moves under the reader.
    for start in range(0, len(keys), STAT_COLUMNS):
        columns = st.columns(STAT_COLUMNS, gap="small")
        for column, key in zip(columns, keys[start:start + STAT_COLUMNS]):
            with column:
                _render_stat(ctx, persona, scope, key, keys, dark)


def _render_stat(ctx: Any, persona: Any, scope: Any, key: str, order: List[str],
                 dark: bool) -> None:
    spec = ctx.registry.get(key)
    if spec is None:
        return
    try:
        if spec.kind == "kpi":
            metric = ctx.metrics.kpi(key, scope, ctx.reporting_date)
            insights.render_kpi(
                metric, dark, _kpi_info(metric, scope), key,
                controls=_controls(ctx, persona.id, key, order, resizable=False))
            return

        config = ctx.store.get(spec.insight_id)
        if config is None:
            return
        insights.render_metric_insight(
            spec, config, ctx.engine.render(config, scope),
            _insight_info(config, scope),
            controls=_controls(ctx, persona.id, key, order, editable=True,
                               resizable=False, table_toggle=False),
            stale=ctx.engine.is_stale(config))
    except Exception:
        log.exception("Stat %s failed", key)
        ui.error_card("This metric is unavailable.", "")


def _ordered(ctx: Any, persona: Any, categories: Sequence[str],
             visibility: Dict[str, bool]) -> List[str]:
    """Visible widget keys for these categories, in the user's saved order."""
    order = ctx.store.order(persona.id)
    specs = [w for category in categories
             for w in ctx.registry.by_category(category, persona.id)
             if visibility.get(w.key, False)]
    return [w.key for w in sorted(specs, key=lambda w: order.get(w.key, 999))]


def _render_canvas_widgets(ctx: Any, persona: Any, scope: Any,
                           visibility: Dict[str, bool], dark: bool) -> None:
    """Insights and user blocks, in saved order, two narrow cards to a row."""
    # Insights and the user's own blocks share one ordered stream, so a heading
    # can sit between two charts rather than in a band of its own.
    keys = [k for k in _ordered(ctx, persona, ("insights", "layout"), visibility)
            if not _is_stat(ctx, k)]
    if not keys:
        ui.empty_state("No insights on your canvas yet.",
                       "Use compose to add one, or create your own with AI.")
        return

    spans = ctx.store.spans(persona.id)
    blocks = {b["id"]: b for b in ctx.store.blocks(persona.id)}

    def width(key: str) -> int:
        spec = ctx.registry.get(key)
        stored = spans.get(key, 0)
        return stored if stored else (spec.span if spec else 1)

    index = 0
    while index < len(keys):
        key = keys[index]
        partner = keys[index + 1] if index + 1 < len(keys) else None
        # A heading always owns its row; two narrow cards share one.
        heading = key in blocks and blocks[key]["kind"] == "heading"
        pair = (not heading and partner is not None and width(key) == 1
                and width(partner) == 1
                and not (partner in blocks and blocks[partner]["kind"] == "heading"))
        if not pair:
            _render_widget(ctx, persona, scope, key, keys, blocks, dark)
            index += 1
            continue
        left, right = st.columns(2, gap="small")
        with left:
            _render_widget(ctx, persona, scope, key, keys, blocks, dark)
        with right:
            _render_widget(ctx, persona, scope, partner, keys, blocks, dark)
        index += 2


def _render_widget(ctx: Any, persona: Any, scope: Any, key: str, order: List[str],
                   blocks: Dict[str, Any], dark: bool) -> None:
    if key in blocks:
        insights.render_block(
            blocks[key],
            controls=[(":material/edit:", "Edit this block",
                       _edit_block, (ctx, blocks[key]))]
            + _controls(ctx, persona.id, key, order, resizable=True))
        return

    spec = ctx.registry.get(key)
    if spec is None or spec.kind != "insight":
        return
    try:
        config = ctx.store.get(spec.insight_id)
        if config is None:
            return
        columns = ctx.engine.filter_options(config, scope)
        insights.render_insight(
            spec, config,
            lambda filters: ctx.engine.render(config, scope, list(filters)),
            dark, columns, _insight_info(config, scope),
            controls=_controls(ctx, persona.id, key, order, editable=True),
            stale=ctx.engine.is_stale(config))
    except Exception:
        log.exception("Insight %s failed to render", key)
        ui.error_card("We could not load this insight.",
                      "The rest of your canvas is unaffected.")


def _toggle_table(widget_key: str) -> None:
    state = dict(session.widget_filter(widget_key))
    state["as_table"] = not state.get("as_table")
    session.set_widget_filter(widget_key, state)


def _cycle_span(ctx: Any, persona_id: str, key: str) -> None:
    spec = ctx.registry.get(key)
    spans = ctx.store.spans(persona_id)
    current = spans.get(key, 0) or (spec.span if spec else 1)
    ctx.store.set_span(persona_id, key, 1 if current >= 2 else 2)


def _move_widget(ctx: Any, persona_id: str, key: str, order: List[str],
                 delta: int) -> None:
    ctx.store.move(persona_id, key, list(order), delta)


def _hide_widget(ctx: Any, key: str) -> None:
    ctx.store.set_visibility(session.persona_id(), key, False)
    session.set_notice("Removed from your canvas")


def _edit_block(ctx: Any, block: Dict[str, str]) -> None:
    """Toggle the inline editor, saving whatever is in the fields on the way out."""
    key = block["id"].replace(".", "-")
    if session.editing_block() == block["id"]:
        title = st.session_state.get("block-title-{}".format(key), block["title"])
        body = st.session_state.get("block-body-{}".format(key), block["body"])
        ctx.store.update_block(block["id"], title, body)
    session.toggle_block_editor(block["id"])


def _add_block(ctx: Any, persona_id: str, kind: str) -> None:
    block_id = ctx.store.add_block(persona_id, kind)
    ctx.store.set_visibility(persona_id, block_id, True)
    session.toggle_block_editor(block_id)


# ======================================================================================
# dialog dispatcher: exactly one dialog per script run
# ======================================================================================

def _dispatch_dialog(ctx: Any, persona: Any, scope: Any, meetings, actions) -> None:
    intent = session.open_dialog()
    if not intent:
        return
    kind, entity = intent

    if kind == "meeting":
        meeting = next((m for m in meetings if m.meeting_id == entity), None)
        if meeting is None:
            session.clear_dialog()
            return
        dialogs.meeting_dialog(
            meeting,
            lambda: ctx.prep.generate(scope, persona, meeting, ctx.reporting_date))

    elif kind == "action":
        action = next((a for a in actions if a.key == entity), None)
        if action is None:
            session.clear_dialog()
            return
        dialogs.action_dialog(
            action,
            lambda: _explain_action(ctx, persona, action),
            lambda action_type: _execute_action(ctx, persona, action, action_type),
        )

    elif kind == "edit":
        config = ctx.store.get(entity)
        if config is None:
            session.clear_dialog()
            return
        dialogs.edit_insight_dialog(
            config,
            lambda instruction: ctx.engine.edit_with_ai(
                config, instruction, scope, persona.id),
            lambda new_config, note: _save_edit(ctx, new_config, note),
        )

    elif kind == "create":
        dialogs.create_insight_dialog(
            lambda question: _generate_insight(ctx, question, scope, persona),
            lambda config: _save_new_insight(ctx, config, persona),
        )

    elif kind == "add":
        visibility = _visibility(ctx, persona.id, ctx.registry.for_persona(persona.id))
        hidden = [w for w in ctx.registry.for_persona(persona.id)
                  if not visibility.get(w.key, False)]
        dialogs.add_widget_dialog(hidden, lambda key: _add_widget(ctx, persona, key))


# ======================================================================================
# actions
# ======================================================================================

def _explain_action(ctx: Any, persona: Any, action: Any) -> Optional[ActionExplanation]:
    def fallback() -> Dict[str, Any]:
        return {
            "what_happened": action.why,
            "why_it_matters": "This sits on {}{}.".format(
                action.account_name or "your queue",
                " and is worth {}".format(money(action.amount)) if action.amount else ""),
            "recommended_action": action.title,
            "generated_by": "prepared",
        }

    bundle = ctx.context.for_account(ctx.scope_for(persona.id), action.account_id,
                                     action.deal_id)
    return ctx.ai.run(
        task=tasks.ACTION_EXPLAIN,
        system=tasks.action_explain_system(ctx.reporting_date.isoformat()),
        user="## The action\n{}\n\nWhy it surfaced: {}\n\n## Evidence\n\n{}".format(
            action.title, action.why, bundle.to_prompt_markdown()),
        cacheable_system=knowledge.narrative_knowledge(),
        cache_inputs={"action": action.key, "context": bundle.context_hash()},
        fallback=fallback,
        persona_id=persona.id,
    )


def _execute_action(ctx: Any, persona: Any, action: Any, action_type: str):
    draft = ""
    if action_type in ("draft_email", "send_recap"):
        draft = _draft_email(ctx, persona, action)
    result = ctx.executor.execute(action, action_type, {"draft": draft})
    return result, draft


def _draft_email(ctx: Any, persona: Any, action: Any) -> str:
    scope = ctx.scope_for(persona.id)
    bundle = ctx.context.for_account(scope, action.account_id, action.deal_id)
    contact = bundle.contacts[0] if bundle.contacts else None
    first = contact.first_name if contact else "there"
    playbook_kind = (action.evidence or {}).get("playbook", "")
    template = sample_message(playbook_kind) if playbook_kind else None

    def fallback() -> Dict[str, Any]:
        body = (render_template(template, first_name=first) if template else
                "Hi {},\n\n{}\n\nWorth a short conversation this week?\n\n{}".format(
                    first, action.why, persona.label))
        return {"subject": action.title[:70], "body": body,
                "to": contact.email if contact else "", "generated_by": "prepared"}

    result = ctx.ai.run(
        task=tasks.EMAIL_DRAFT,
        system=tasks.email_draft_system(persona.label,
                                        render_template(template or "", first_name=first)),
        user="Write the email for this action: {}\n\nContext:\n{}\n\n## Evidence\n\n{}".format(
            action.title, action.why, bundle.to_prompt_markdown()),
        cacheable_system=knowledge.narrative_knowledge(),
        cache_inputs={"action": action.key, "context": bundle.context_hash()},
        fallback=fallback,
        persona_id=persona.id,
    )
    if result is None:
        return ""
    to = result.to or (contact.email if contact else "")
    return "To: {}\nSubject: {}\n\n{}".format(to, result.subject, result.body)


# ======================================================================================
# insights lifecycle
# ======================================================================================

def _generate_insight(ctx: Any, question: str, scope: Any, persona: Any):
    config = ctx.engine.create_from_prompt(question, scope, persona.id)
    return config, ctx.engine.render(config, scope)


def _save_new_insight(ctx: Any, config: Any, persona: Any) -> None:
    config.personas = [persona.id]
    ctx.store.save_new(config)
    refresh_insight_widgets(ctx.registry, ctx.store)
    ctx.store.set_visibility(persona.id, config.id, True)


def _save_edit(ctx: Any, config: Any, note: str) -> None:
    ctx.store.save_version(config, note)
    refresh_insight_widgets(ctx.registry, ctx.store)


def _add_widget(ctx: Any, persona: Any, key: str) -> None:
    ctx.store.set_visibility(persona.id, key, True)
    session.clear_dialog()


def _toggle_widget(ctx: Any, persona_id: str, key: str) -> None:
    current = ctx.store.layout(persona_id)
    default = key in _context().persona(persona_id).default_widgets
    ctx.store.set_visibility(persona_id, key, not current.get(key, default))


def _reset_layout(ctx: Any, persona_id: str) -> None:
    ctx.store.reset_layout(
        persona_id,
        list(ctx.persona(persona_id).default_widgets),
        [w.key for w in ctx.registry.for_persona(persona_id)])
    session.set_notice("Canvas restored to defaults")


# ======================================================================================
# the answer path
# ======================================================================================

def _config_from_insight(ctx: Any, persona: Any, insight: Any, question: str):
    import uuid

    from intellia.models.insight import (
        InsightConfig, InsightMetadata, RefreshSpec, ScopeBinding, VizSpec,
    )
    return InsightConfig(
        id="ins-" + uuid.uuid4().hex[:12],
        title=insight.title or "Pinned answer",
        subtitle=insight.description,
        description=insight.description,
        generated_sql=insight.sql,
        nl_definition=question,
        category="insights",
        schema_fingerprint=ctx.db.schema_fingerprint(),
        viz=VizSpec(type=insight.visualization or "table", x=insight.x or None,
                    y=insight.y or None, unit=insight.unit or "#"),
        scope_binding=ScopeBinding(persona_scoped=True),
        refresh=RefreshSpec(cadence_label=insight.refresh or "Hourly"),
        metadata=InsightMetadata(source="ai", created_by_persona=persona.id,
                                 model=ctx.ai.mode_label,
                                 calculation=insight.calculation),
        personas=[persona.id],
    )


def _answer(ctx: Any, ask: AskService, scope: Any, persona: Any, question: str,
            dark: bool) -> Any:
    """One conversational turn.

    Text to SQL runs FIRST when the question is data shaped, and the rows it
    returns are handed to the answer prompt. Doing it the other way round is what
    produced an answer saying "I only have totals" directly above a chart of the
    breakdown: two model calls looking at two different sets of facts. The rows
    are computed once and both the prose and the chart read from them.
    """
    rows_markdown, preview = "", None
    if wants_insight(question):
        preview = _build_preview(ctx, persona, scope, question, dark,
                                 _prior_block())
        if preview is not None:
            frame = preview[1].frame
            # A query that ran and matched nothing is a real answer. Passing the
            # empty string here made it indistinguishable from no query at all,
            # and the model then said it had not been given the figures.
            rows_markdown = (frame_to_markdown(frame) if not frame.empty
                             else tasks.EMPTY_RESULT)

    try:
        answer = ask.ask(question, scope, persona, ctx.reporting_date,
                         result_table=rows_markdown)
    except Exception:
        log.exception("Ask failed")
        return None
    if answer is None:
        return None
    if preview is not None:
        insight, rendered, chart = preview
        answer.insight = insight
        session.cache_preview(question, rendered, chart)
    return answer


def _prior_block() -> str:
    """The previous answered turn, rendered for the generator prompt."""
    prior = session.last_answered_turn()
    if prior is None:
        return ""
    return tasks.prior_turn_block(prior["question"], prior["sql"], prior["viz"])


def _build_preview(ctx: Any, persona: Any, scope: Any, question: str, dark: bool,
                   prior: str = ""):
    """Generate SQL for the question, run it, and build its chart."""
    try:
        config = ctx.engine.create_from_prompt(question, scope, persona.id,
                                               prior=prior)
        rendered = ctx.engine.render(config, scope)
        # An empty result is kept. Only a query that could not run is discarded:
        # dropping the empty one hid both the card and the SQL, so "none" looked
        # identical to "I could not answer that".
        if not rendered.ok:
            return None
        from intellia.models.ai import GeneratedInsight
        insight = GeneratedInsight(
            title=config.title, description=config.description,
            sql=config.generated_sql, x=config.viz.x or "", y=config.viz.y or "",
            visualization=config.viz.type, unit=config.viz.unit,
            calculation=config.metadata.calculation)
        chart = (charts.build(rendered.frame, config.viz.type, config.viz.x,
                              config.viz.y, config.viz.unit, dark)
                 if not rendered.frame.empty else None)
        return insight, rendered, chart
    except Exception:
        log.info("No insight could be generated for: %s", question)
        return None


def _preview(ctx: Any, persona: Any, scope: Any, dark: bool, insight: Any):
    """Re-render a pinned answer's chart on a later pass.

    The first pass caches what it already computed, so replaying a thread does
    not re-run the query for every turn on every rerun.
    """
    cached = session.cached_preview(insight.sql)
    if cached is not None:
        return cached
    config = _config_from_insight(ctx, persona, insight, "")
    rendered = ctx.engine.render(config, scope)
    if not rendered.ok or rendered.frame.empty:
        # Empty is still rendered by the caller, which shows the card and says so;
        # there is simply no chart to build from no rows.
        return rendered, None
    chart = charts.build(rendered.frame, config.viz.type, config.viz.x,
                         config.viz.y, config.viz.unit, dark)
    return rendered, chart


def _pin(ctx: Any, persona: Any, insight: Any, question: str) -> None:
    if not insight or not insight.sql:
        return
    _save_new_insight(ctx, _config_from_insight(ctx, persona, insight, question), persona)
    session.set_notice("Pinned to your canvas")


# ======================================================================================
# views
# ======================================================================================

def _my_day(ctx: Any, persona: Any, scope: Any, dark: bool, widgets, visibility,
            on_ask):
    """The canvas. Returns today's meetings and actions for the dispatcher."""
    chrome.render_greeting(persona, ctx.reporting_date, scope.label)
    chrome.render_ask(on_ask)

    composer.render_composer(
        widgets, visibility,
        on_toggle=lambda key: _toggle_widget(ctx, persona.id, key),
        on_select=session.set_compose_tab,
        on_create=lambda: session.set_dialog("create"),
        on_add=lambda: session.set_dialog("add"),
        on_add_block=lambda kind: _add_block(ctx, persona.id, kind),
    )
    _band_pulse()

    if visibility.get("component.daily_brief", True):
        panels.render_brief(
            lambda: _safe_brief(ctx, scope, persona, ctx.reporting_date),
            ctx.ai.mode_label,
            on_refresh=lambda: _refresh_brief(ctx),
            info_pairs=_panel_info(
                "Ranked summary of what changed since yesterday.",
                "Calendar, mail, CRM and signals for {}".format(scope.label),
                "Custom panel, model ranks and writes, references validated",
                ctx.ai.mode_label),
            controls=[(":material/close:", "Remove from canvas", _hide_widget,
                       (ctx, "component.daily_brief"))])

    show_meetings = visibility.get("component.meetings", True)
    show_actions = visibility.get("component.actions", True)
    meetings = (ctx.calendar.get_meetings_for_day(scope, ctx.reporting_date,
                                                  persona.user_id)
                if show_meetings else [])
    actions = (ctx.actions.build_queue(scope, ctx.reporting_date, limit=10)
               if show_actions else [])

    if show_meetings or show_actions:
        panels.render_today(
            meetings, actions, _attendee_names(ctx, scope), session.executed,
            show_meetings, show_actions,
            on_meeting=lambda mid: session.set_dialog("meeting", mid),
            on_action=lambda key: session.set_dialog("action", key),
            on_join=_join_meeting,
            info_pairs=_panel_info(
                "Today's calendar beside the ranked action queue.",
                "Outlook calendar, Outlook mail, CRM, signals and tasks",
                "Custom panel, deterministic assembly and ranking",
                "Deterministic (no model call)"),
            controls=[(":material/close:", "Remove from canvas", _hide_today,
                       (ctx, show_meetings, show_actions))])

    # The band is only drawn when it has something in it. Drawing the header
    # unconditionally left an "Insights" title over an empty-state card once the
    # last widget was removed, which reads as a section that failed to load
    # rather than as a canvas the reader has cleared.
    if _canvas_has_insights(ctx, persona, visibility):
        with st.container(key="band-insights"):
            ui.section_header("Insights", anchor="band-insights")
            _render_stats(ctx, persona, scope, visibility, dark)
            _render_canvas_widgets(ctx, persona, scope, visibility, dark)
    elif not (show_meetings or show_actions):
        ui.empty_state("Your canvas is empty.",
                       "Add cards with compose, or describe one and let Intellia "
                       "build it.")

    return meetings, actions


def _canvas_has_insights(ctx: Any, persona: Any, visibility: Dict[str, bool]) -> bool:
    """Anything at all in the insights band: a stat tile, a card or a user block."""
    return bool(_ordered(ctx, persona, ("insights", "layout"), visibility))


def _join_meeting(target: str) -> None:
    """Placeholder for the conferencing link.

    The seam is real (the calendar connector carries the location); only the link
    is mocked, and it says so rather than opening nothing and looking broken.
    """
    session.set_notice("{} link is mocked in this prototype".format(target))


def _hide_today(ctx: Any, had_meetings: bool, had_actions: bool) -> None:
    """One control removes the widget the user is looking at, both halves of it."""
    for key, shown in (("component.meetings", had_meetings),
                       ("component.actions", had_actions)):
        if shown:
            ctx.store.set_visibility(session.persona_id(), key, False)
    session.set_notice("Removed from your canvas")


def _chat_view(ctx: Any, ask: AskService, persona: Any, scope: Any, dark: bool,
               on_ask) -> None:
    thread = session.current_thread()
    if thread is None:
        session.go_home()
        return

    chrome.page_header(thread["title"], "Grounded in your evidence and your metrics")
    chat.render_thread(
        thread, ctx.ai.mode_label,
        answer_fn=lambda q: _answer(ctx, ask, scope, persona, q, dark),
        preview_fn=lambda insight: _preview(ctx, persona, scope, dark, insight),
        on_ask=on_ask,
        on_pin=lambda insight, q: _pin(ctx, persona, insight, q or thread["title"]),
    )
    # Bottom-pinned, not inline: a conversation's composer belongs at the foot of
    # the screen and stays there while the thread scrolls under it. on_submit for
    # the same reason as the hero bar: the turn has to be queued before the thread
    # above it renders, not after.
    # Disabled rather than hidden once the chat is full: a composer that vanishes
    # reads as a bug, and the placeholder is where the reason belongs. on_ask
    # still refuses, so this is the signal, not the enforcement.
    full = session.thread_is_full()
    st.chat_input(
        "Start a new chat to keep asking" if full else "Ask a follow up",
        key="thread-input", disabled=full,
        on_submit=chrome.submit_question, args=("thread-input", on_ask))


def _portfolio_rows(ctx: Any, scope: Any) -> List[Dict[str, Any]]:
    """One row per account: the Customer 360 shape, assembled deterministically."""
    rows: List[Dict[str, Any]] = []
    for account in ctx.accounts.list_by_scope(scope, limit=200):
        deals = ctx.deals.by_account(scope, account.account_id)
        open_deals = [d for d in deals if not str(d.stage).startswith("Stage 5")]
        furthest = max(open_deals, key=lambda d: str(d.stage)) if open_deals else None
        next_step = next((d.next_step for d in open_deals if d.next_step), "")
        rows.append({
            "account": account.account_name,
            "industry": account.industry,
            "segment": account.segment,
            "region": account.region,
            "health": int(getattr(account, "health_score", 0) or 0),
            "arr": float(account.arr or 0),
            "open_pipeline": float(sum(d.amount for d in open_deals)),
            "open_deals": len(open_deals),
            "stage": furthest.stage if furthest else "No open deal",
            "next_step": truncate(next_step, 60) or "Not set",
            "renewal": relative_day(account.renewal_date) or "Not set",
        })
    return rows


# ======================================================================================
# main
# ======================================================================================

def main() -> None:
    session.init()

    dark = _is_dark()
    _load_styles(dark)
    charts.register_themes()
    charts.use_theme(dark)

    ctx = _context()
    ask = _ask_service(ctx)

    persona = ctx.persona(session.persona_id())
    scope = ctx.scope_for(persona.id)

    _register_blocks(ctx, persona.id)
    widgets = ctx.registry.for_persona(persona.id)
    visibility = _visibility(ctx, persona.id, widgets)

    def on_ask(question: str) -> None:
        text = (question or "").strip()
        if not text:
            return
        if session.view() == "chat" and session.current_thread() is not None:
            # Every route into a thread lands here: the rail, the follow-up chips
            # and the composer. Guarding at the single entry point is what stops a
            # sixth question arriving from whichever one was not disabled.
            if session.thread_is_full():
                session.set_notice(
                    "This chat is at its {} question limit. Start a new chat to "
                    "keep going.".format(session.MAX_QUESTIONS_PER_THREAD))
                return
            session.queue_question(text)
        else:
            session.start_thread(text)

    sidebar.render(persona, ctx.ai.mode_label, on_ask)

    notice = session.take_notice()
    if notice:
        st.toast(notice, icon=":material/check_circle:")

    view = session.view()
    meetings, actions = [], []

    if view == "chat":
        _chat_view(ctx, ask, persona, scope, dark, on_ask)
    elif view == "projects":
        views.render_portfolio(_portfolio_rows(ctx, scope))
    elif view == "skills":
        views.render_skills(ctx.ai.mode_label, ctx.ai.live,
                            model_for=lambda name: _model_label(ctx, name))
    elif view == "digests":
        views.render_digests()
    elif view == "apps":
        views.render_apps()
    elif view == "updates":
        views.render_updates()
    elif view == "settings":
        views.render_settings(
            persona, ctx.ai.mode_label, ctx.ai.live, scope.label, ctx.reporting_date,
            len(widgets), lambda: _reset_layout(ctx, persona.id),
            flagship_model=ctx.settings.model, fast_model=ctx.settings.fast_model)
    else:
        meetings, actions = _my_day(
            ctx, persona, scope, dark, widgets, visibility, on_ask)

    # Not in a thread: the composer is pinned to the foot of the screen there, and
    # a footer above it would float in the middle of an empty conversation.
    if view != "chat":
        st.html('<div class="ix-foot"><p class="ix-meta">Intellia (Beta)</p></div>')

    # Exactly one dialog, dispatched last.
    _dispatch_dialog(ctx, persona, scope, meetings, actions)


def _model_label(ctx: Any, task_name: str) -> str:
    """Which tier a named task runs on, for the skills catalogue."""
    for task in (tasks.DAILY_BRIEF, tasks.MEETING_PREP, tasks.ACTION_EXPLAIN,
                 tasks.EMAIL_DRAFT, tasks.INSIGHT_SQL, tasks.ASK):
        if task.name == task_name:
            return ctx.ai.model_for(task)
    return ctx.ai.mode_label


def _register_blocks(ctx: Any, persona_id: str) -> None:
    """Publish the user's own blocks as widgets.

    Registering them means ordering, width, visibility and the composer all treat
    a hand-written note exactly like a generated chart, with no special cases.
    """
    from intellia.insights.widget_registry import DEFAULT_DEPARTMENT, WidgetSpec

    live = {b["id"] for b in ctx.store.blocks(persona_id)}
    for block in ctx.store.blocks(persona_id):
        ctx.registry.register(WidgetSpec(
            key=block["id"],
            title=block["title"] or ("Section title" if block["kind"] == "heading"
                                     else "Note"),
            category="layout", kind="block",
            subtitle="Your own {}".format(
                "heading" if block["kind"] == "heading" else "text block"),
            short_title=block["title"] or "Block",
            icon=(":material/title:" if block["kind"] == "heading"
                  else ":material/notes:"),
            department=DEFAULT_DEPARTMENT,
            default_visible_for=[persona_id],
            span=2 if block["kind"] == "heading" else 1,
            source="manual",
        ))
    # Drop registry entries for blocks that were deleted.
    for spec in list(ctx.registry.all()):
        if spec.kind == "block" and spec.key not in live:
            ctx.registry.unregister(spec.key)


def _safe_brief(ctx: Any, scope: Any, persona: Any, as_of: Any) -> Any:
    try:
        return ctx.brief.generate(scope, persona, as_of)
    except Exception:
        log.exception("Daily brief failed")
        return None


def _refresh_brief(ctx: Any) -> None:
    ctx.ai.cache.clear()
    session.set_notice("Brief regenerated")


if __name__ == "__main__":
    main()
