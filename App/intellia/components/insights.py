"""Insights band.

Every card carries the same control strip in its top right corner, as icons
rather than a dropdown: definition, edit with AI, chart or table, width, move up,
move down, remove. One click each, nothing hidden behind a menu.

**The control strip renders OUTSIDE the card's fragment, and that is load
bearing.** A widget inside a fragment only reruns that fragment, so a button in
there can set `session.set_dialog(...)` and the dispatcher in ``app.py`` will
never see it: edit-with-AI silently does nothing, and remove appears to do
nothing until some unrelated interaction forces a full rerun. Only the body
(filter chips, chart, footer) stays in the fragment, which is what a filter
change should re-execute in isolation.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Sequence

import pandas as pd
import streamlit as st

from intellia.components import primitives as ui
from intellia.insights.widget_registry import WidgetSpec
from intellia.models.insight import FilterSpec
from intellia.services.metrics_service import Metric
from intellia.state import session
from intellia.theme import charts
from intellia.insights.visualization_selector import infer_unit
from intellia.utils.formatting import by_unit, humanize_column


def render_kpi(metric: Metric, dark: bool, info_pairs: Sequence[Any],
               widget_key: str, controls: Sequence[Any] = ()) -> None:
    """A stat tile: value, movement, and either a trend strip or a meter."""
    key = widget_key.replace(".", "-")
    value = (by_unit(metric.value, metric.unit) if metric.value is not None
             else "Target met")
    delta, direction = _delta(metric)

    with ui.card("kpi-{}".format(key)):
        head = st.container(key="row-head-kpi-{}".format(key), horizontal=True,
                            vertical_alignment="top")
        with head:
            st.html(ui.kpi_html(metric.label, value, metric.caption, delta, direction))
            ui.info_popover(key, metric.label, info_pairs)
            ui.control_strip(key, controls)

        # A fixed-height slot either way, so a tile with a trend and a tile with
        # a meter are the same height and the row lines up.
        spark = charts.sparkline(metric.sparkline, dark) if metric.sparkline else None
        if spark is not None:
            st.altair_chart(spark, use_container_width=True, theme=None)
        else:
            st.html(ui.meter_slot(_meter_fraction(metric.value, metric.unit)))

        st.html(ui.card_footer("Semantic layer"))


def render_metric_insight(spec: WidgetSpec, config: Any, rendered: Any,
                          info_pairs: Sequence[Any], controls: Sequence[Any] = (),
                          stale: bool = False) -> None:
    """A created insight whose result is one number, drawn as a stat tile.

    This is the same tile a built-in KPI gets, and deliberately so: it was the
    only widget in the app with a second, thinner implementation of the stat card
    (a bare value, no movement, and the subtitle printed twice, once in the card
    header and once again as the caption). Sharing ``kpi_html`` and the meter slot
    means a created stat card cannot drift from the ones beside it.

    There is no fragment here. A single-row metric has no categorical column to
    filter on, so the body never re-executes on its own and the value has to be
    known before the header is written.
    """
    key = spec.key.replace(".", "-")
    value, delta, direction = _insight_metric(config, rendered)

    with ui.card("kpi-{}".format(key)):
        head = st.container(key="row-head-kpi-{}".format(key), horizontal=True,
                            vertical_alignment="top")
        with head:
            # The subtitle is the caption and nothing else, so it appears once.
            st.html(ui.kpi_html(spec.title, value, spec.subtitle, delta, direction))
            ui.info_popover(key, spec.title, info_pairs, sql=config.generated_sql)
            ui.control_strip(key, controls)

        if stale:
            ui.error_card("This insight may be out of date.",
                          "The data model changed since it was created. "
                          "Use edit with AI to rebuild it.")
        elif not rendered.ok:
            ui.error_card("We could not load this metric.", rendered.error or "")
        else:
            st.html(ui.meter_slot(_meter_fraction(_cell(rendered.frame, config.viz.y),
                                                  config.viz.unit)))

        st.html(ui.card_footer(config.metadata.data_source))


def _meter_fraction(value: Any, unit: str) -> Any:
    """A percentage gets a meter; everything else gets the empty slot."""
    return float(value) / 100.0 if unit == "%" and value is not None else None


def _cell(frame: Any, column: Any) -> Any:
    """The one value on a single-row result, or None if it is not there.

    Falling back to the first column is deliberate and is what keeps a card saved
    under the old contract on screen. Replay re-derives the viz spec, so a card
    whose query outgrew a single number arrives here with no ``y`` at all; it then
    shows its leading measure, correctly formatted, with no movement, instead of
    an error where a number used to be. Rebuilding it with AI is what gets the
    delta back.
    """
    if frame is None or getattr(frame, "empty", True):
        return None
    name = column if column in frame.columns else str(frame.columns[0])
    try:
        raw = frame.iloc[0][name]
        return None if pd.isna(raw) else float(raw)
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def _delta(metric: Metric):
    """Period over period from the metric's own trend. No model, no guessing."""
    series = [v for v in (metric.sparkline or []) if v is not None]
    if len(series) < 2 or not series[-2]:
        return "", "flat"
    return _delta_text(100.0 * (series[-1] - series[-2]) / abs(series[-2]), "MoM")


def _insight_metric(config: Any, rendered: Any):
    """Value and movement for a metric insight, read off its own result row.

    The comparison is a second column the query returned, so the movement is
    arithmetic over two numbers that came out of SQL together. The model is not
    asked for a percentage and never computes one.
    """
    viz = config.viz
    if not rendered.ok:
        return "n/a", "", "flat"

    current = _cell(rendered.frame, viz.y)
    if current is None:
        return "n/a", "", "flat"
    value = by_unit(current, viz.unit)

    if not viz.compare or viz.compare not in rendered.frame.columns:
        return value, "", "flat"
    other = _cell(rendered.frame, viz.compare)
    if other is None:
        return value, "", "flat"

    if viz.compare_kind == "change":
        change = other
    elif other:
        change = 100.0 * (current - other) / abs(other)
    else:
        return value, "", "flat"

    delta, direction = _delta_text(change, viz.delta_label or "vs prior")
    return value, delta, direction


def _delta_text(change: float, label: str):
    """One wording for movement, so both kinds of stat tile read the same."""
    if abs(change) < 0.5:
        return "flat", "flat"
    return "{:+.0f}% {}".format(change, label).strip(), "up" if change > 0 else "down"


def render_insight(spec: WidgetSpec, config: Any,
                   load: Callable[[Sequence[FilterSpec]], Any],
                   dark: bool, filter_columns: Sequence[str],
                   info_pairs: Sequence[Any],
                   controls: Sequence[Any] = (),
                   stale: bool = False) -> None:
    """One insight card: header and controls, then the body inside a fragment.

    ``load(filters)`` runs the saved SQL. It is called INSIDE the fragment so a
    filter change re-executes only this card's query. Streamlit reruns the
    fragment natively when a widget inside it changes, so no explicit
    ``st.rerun`` is needed (and calling one on first paint is an error).
    """
    key = spec.key.replace(".", "-")

    with ui.card("insight-{}".format(key)):
        head = st.container(key="row-head-ins-{}".format(key), horizontal=True,
                            vertical_alignment="top")
        with head:
            st.html(ui.card_header(spec.title, spec.subtitle))
            ui.info_popover(key, spec.title, info_pairs, sql=config.generated_sql)
            ui.control_strip(key, controls)

        if stale:
            ui.error_card("This insight may be out of date.",
                          "The data model changed since it was created. "
                          "Use edit with AI to rebuild it.")

        def _body_fragment() -> None:
            base = load([])
            if not base.ok:
                ui.error_card("We could not load this insight.", base.error or "")
                return
            if base.frame.empty:
                ui.empty_state("Nothing to show yet.", "This insight returned no rows.")
                return

            chosen = _filter_row(spec, key, filter_columns, base.frame)
            rendered = load(chosen) if chosen else base

            if not rendered.ok:
                ui.error_card("We could not apply that filter.", rendered.error or "")
                return
            if rendered.frame.empty:
                ui.empty_state("No rows match this filter.",
                               "Clear the filter to see everything again.")
                return

            _body(spec, rendered, rendered.frame, dark, key)

            meta = rendered.config.metadata
            st.html(ui.card_footer("{} · {} row{}".format(
                meta.data_source, rendered.result.row_count,
                "" if rendered.result.row_count == 1 else "s")))

        st.fragment(_body_fragment)()


def render_block(block: Dict[str, str], controls: Sequence[Any] = ()) -> None:
    """A user-authored heading or note.

    Editing is inline rather than in a dialog: the block *is* the editor once you
    open it, so there is no modal between the user and two text fields.
    """
    key = block["id"].replace(".", "-")
    editing = session.editing_block() == block["id"]

    if block["kind"] == "heading" and not editing:
        row = st.container(key="row-head-block-{}".format(key), horizontal=True,
                           vertical_alignment="center")
        with row:
            st.html('<p class="ix-block-heading">{}</p>'.format(
                ui.esc_text(block["title"])))
            ui.control_strip(key, controls)
        return

    with ui.card("block-{}".format(key)):
        row = st.container(key="row-head-block-{}".format(key), horizontal=True,
                           vertical_alignment="top")
        with row:
            if not editing:
                st.html('<p class="ix-card-title">{}</p>'
                        '<p class="ix-block-body">{}</p>'.format(
                            ui.esc_text(block["title"]),
                            ui.esc_text(block["body"]).replace("\n", "<br>")))
            else:
                st.html('<p class="ix-eyebrow">Editing this block</p>')
            ui.control_strip(key, controls)

        if editing:
            st.text_input("Title", value=block["title"],
                          key="block-title-{}".format(key), label_visibility="collapsed",
                          placeholder="Title")
            if block["kind"] == "note":
                st.text_area("Body", value=block["body"], height=76,
                             key="block-body-{}".format(key),
                             label_visibility="collapsed", placeholder="Body")


def _filter_row(spec: WidgetSpec, key: str, columns: Sequence[str],
                frame: pd.DataFrame) -> List[FilterSpec]:
    """Filter chips over a categorical column present in the result.

    A filter can only reference a column the query actually selects. That limit is
    surfaced honestly (the chips only offer real result columns) rather than
    papered over by regex-rewriting the base query's WHERE clause.
    """
    candidates = [c for c in columns
                  if c in frame.columns
                  and not pd.api.types.is_numeric_dtype(frame[c])
                  and 1 < frame[c].nunique() <= 8]
    if not candidates:
        return []
    column = candidates[0]
    options = sorted(str(v) for v in frame[column].dropna().unique())

    # Changing this widget reruns the enclosing fragment automatically.
    chosen = st.pills(humanize_column(column), options, selection_mode="multi",
                      key="flt-{}".format(key), label_visibility="collapsed")
    if not chosen:
        return []
    return [FilterSpec(column=column, op="in", values=list(chosen),
                       label=humanize_column(column))]


def _body(spec: WidgetSpec, rendered: Any, frame: pd.DataFrame,
          dark: bool, key: str) -> None:
    viz = rendered.config.viz
    force_table = session.widget_filter(spec.key).get("as_table")

    if viz.type == "metric" and not force_table:
        # The canvas routes metric insights to render_metric_insight, so this is
        # only reached if one is shown as a full card anyway. No caption here:
        # the card header above already carries the subtitle.
        value, delta, direction = _insight_metric(rendered.config, rendered)
        st.html(ui.kpi_html("", value, "", delta, direction))
        return

    chart = None if force_table else charts.build(
        frame, viz.type, viz.x, viz.y, viz.unit, dark)

    if chart is not None:
        st.altair_chart(chart, use_container_width=True, theme=None)
        return

    st.dataframe(
        frame,
        hide_index=True,
        width="stretch",
        # Header plus whole rows only: a part-row at the bottom reads as a bug.
        height=ui.table_height(len(frame)),
        column_config=column_config(frame),
    )


def column_config(frame: pd.DataFrame) -> Dict[str, Any]:
    """Per-column formatting, inferred per column and never from the card.

    The card's own unit must NOT decide this. A money insight that also returns
    "days in stage" would render 21 days as $21, which is exactly the kind of
    number a seller would act on without questioning it. ``infer_unit`` reads the
    column, which is the only thing that knows what it holds.

    ``step=1`` is what drops the trailing ".00": Streamlit takes display
    precision for a float column from the step, not from the format preset.
    """
    config: Dict[str, Any] = {}
    for column in frame.columns:
        label = humanize_column(column)
        series = frame[column]
        if not pd.api.types.is_numeric_dtype(series):
            config[column] = st.column_config.TextColumn(label)
            continue

        lowered = str(column).lower()
        unit = infer_unit(str(column), series)
        # printf has no thousands flag: "%,.0f" renders as a cell error, so money
        # and counts use Streamlit's locale-aware presets instead.
        if "score" in lowered or "probability" in lowered:
            config[column] = st.column_config.ProgressColumn(
                label, min_value=0,
                max_value=float(max(100, series.max() or 100)), format="%d")
        elif unit == "%":
            config[column] = st.column_config.NumberColumn(label, format="%.1f%%")
        elif unit == "x":
            config[column] = st.column_config.NumberColumn(label, format="%.2fx")
        elif unit == "$":
            config[column] = st.column_config.NumberColumn(
                label, format="dollar", step=1)
        else:
            config[column] = st.column_config.NumberColumn(
                label, format="localized", step=1)
    return config
