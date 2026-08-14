"""Scope isolation, insight replay, filters and versioning."""

from __future__ import annotations

import pandas as pd
import pytest

from intellia.ai.llm_provider import LLMRequest
from intellia.insights import filters as filter_mod
from intellia.insights import visualization_selector as viz
from intellia.models.insight import FilterSpec, InsightConfig, VizSpec
from intellia.utils.errors import SqlSafetyError
from intellia.utils.formatting import short_sentence


# -- scope ------------------------------------------------------------------------------

def test_rep_scope_excludes_other_owners(db, scope_rep):
    with db.reader(scope_rep) as conn:
        owners = {r[0] for r in conn.execute(
            "SELECT DISTINCT owner_id FROM deals").fetchall()}
    assert owners == {"USR-3002"}


def test_manager_scope_is_the_team_union(db, scope_rep, scope_manager):
    with db.reader(scope_manager) as conn:
        owners = {r[0] for r in conn.execute(
            "SELECT DISTINCT owner_id FROM deals").fetchall()}
        users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    assert "USR-3002" in owners
    assert owners.issubset(set(scope_manager.user_ids))
    # users is scoped too, or a "pipeline by rep" query would enumerate the company.
    assert users == len(scope_manager.user_ids)


def test_scope_cannot_be_escaped_via_main(db, scope_rep):
    with db.reader(scope_rep) as conn:
        scoped = conn.execute("SELECT COUNT(*) FROM deals").fetchone()[0]
    with db.raw_reader() as conn:
        total = conn.execute("SELECT COUNT(*) FROM deals").fetchone()[0]
    assert scoped < total
    with pytest.raises(Exception):
        with db.reader(scope_rep, sandbox=True) as conn:
            conn.execute("SELECT COUNT(*) FROM main.deals").fetchall()


# -- replay -----------------------------------------------------------------------------

class ExplodingProvider:
    name = "exploding"
    available = True
    model = "none"

    def complete(self, request: LLMRequest):
        raise AssertionError("the LLM must not be called when replaying an insight")


def test_saved_insight_replays_without_llm(app_context, scope_rep):
    """The core cost guarantee: rendering never reaches a provider."""
    original = app_context.ai.provider
    app_context.ai.provider = ExplodingProvider()
    try:
        for config in app_context.store.list_all("rep"):
            rendered = app_context.engine.render(config, scope_rep)
            assert rendered.ok, "{} failed: {}".format(config.id, rendered.error)
    finally:
        app_context.ai.provider = original


def test_every_builtin_renders_for_both_personas(app_context):
    for persona_id in ("rep", "manager"):
        scope = app_context.scope_for(persona_id)
        for config in app_context.store.list_all(persona_id):
            rendered = app_context.engine.render(config, scope)
            assert rendered.ok, "{}/{}: {}".format(persona_id, config.id, rendered.error)


# -- filters ----------------------------------------------------------------------------

def test_filter_values_are_bound_not_interpolated(app_context, scope_rep):
    """A value that looks like SQL is just a string that matches nothing."""
    config = app_context.store.get("insight.pipeline_by_stage")
    hostile = FilterSpec(column="stage", op="eq", values=["'; DROP TABLE deals --"])
    rendered = app_context.engine.render(config, scope_rep, [hostile])
    assert rendered.ok
    assert rendered.result.row_count == 0

    with app_context.db.raw_reader() as conn:
        assert conn.execute("SELECT COUNT(*) FROM deals").fetchone()[0] > 0


def test_filter_rejects_unknown_column():
    with pytest.raises(SqlSafetyError):
        filter_mod.compile_filters(
            [FilterSpec(column="secret", op="eq", values=["x"])], ["stage", "amount"])


def test_filter_rejects_unknown_operator():
    with pytest.raises(SqlSafetyError):
        filter_mod.compile_filters(
            [FilterSpec(column="stage", op="; drop", values=["x"])], ["stage"])


def test_in_filter_expands_placeholders():
    where, params = filter_mod.compile_filters(
        [FilterSpec(column="stage", op="in", values=["a", "b", "c"])], ["stage"])
    assert where.count("?") == 3
    assert params == ["a", "b", "c"]


def test_contains_escapes_like_wildcards():
    _, params = filter_mod.compile_filters(
        [FilterSpec(column="stage", op="contains", values=["100%_x"])], ["stage"])
    assert params == ["%100\\%\\_x%"]


def test_filters_are_deterministic(app_context, scope_rep):
    config = app_context.store.get("insight.pipeline_by_stage")
    spec = [FilterSpec(column="stage", op="in", values=["Stage 1 - Discovery"])]
    first = app_context.engine.render(config, scope_rep, spec).frame
    second = app_context.engine.render(config, scope_rep, spec).frame
    pd.testing.assert_frame_equal(first, second)


# -- visualization ----------------------------------------------------------------------

@pytest.mark.parametrize("frame,expected", [
    (pd.DataFrame({"total": [42.0]}), "metric"),
    (pd.DataFrame({"stage": list("abc"), "v": [1.0, 2.0, 3.0]}), "hbar"),
    (pd.DataFrame({"month": ["2026-01", "2026-02"], "v": [1.0, 2.0]}), "line"),
    (pd.DataFrame({"a": list("abcdefghij") * 4,
                   "v": [float(i) for i in range(40)]}), "table"),
])
def test_visualization_follows_data_shape(frame, expected):
    assert viz.select(frame).type == expected


@pytest.mark.parametrize("column,unit", [
    # "generated" contains "rate" and "shared" contains "share": a raw substring
    # test typed a six figure sum as a percentage and a headcount as one too.
    ("quarter_pipeline_generated", "$"),
    ("shared_accounts", "#"),
    ("win_rate_pct", "%"),
    ("avg_deal_size", "$"),
    ("coverage", "x"),
    ("days_in_stage", "#"),
])
def test_unit_hints_match_words_not_fragments(column, unit):
    assert viz.infer_unit(column) == unit


@pytest.mark.parametrize("column,kind", [
    ("prior_month_pipeline", "prior"),
    ("last_quarter_bookings", "prior"),
    ("mom_change_pct", "change"),
    ("pipeline_created", ""),
    ("changed_deals", ""),          # a word ending in "changed" is not a delta
])
def test_comparison_columns_are_recognised(column, kind):
    assert viz.comparison_kind(column) == kind


def test_metric_keeps_its_comparison_column():
    frame = pd.DataFrame({"pipeline_created": [146000.0],
                          "prior_month_pipeline_created": [118000.0]})
    spec = viz.select(frame)
    assert spec.type == "metric"
    assert spec.y == "pipeline_created"
    assert spec.compare == "prior_month_pipeline_created"
    assert spec.compare_kind == "prior"
    assert spec.delta_label == "MoM"


def test_the_baseline_is_never_the_headline_number():
    """Column order in the SELECT must not decide which number the tile shows."""
    frame = pd.DataFrame({"prior_month_bookings": [100.0], "bookings": [130.0]})
    spec = viz.select(frame)
    assert spec.y == "bookings" and spec.compare == "prior_month_bookings"


def test_three_measures_on_one_row_stay_a_table():
    """A tile shows one number, so hiding two others would read as a bug."""
    frame = pd.DataFrame({"a_amount": [1.0], "b_amount": [2.0], "c_amount": [3.0]})
    assert viz.select(frame).type == "table"
    assert viz.select(frame, "metric").type == "table"


def test_metric_shape_is_re_derived_on_replay(app_context, scope_rep):
    """A saved card that claims one number over a wider row falls back honestly.

    The old metric renderer printed ``frame.iloc[0, 0]`` and ignored its own
    ``viz.y``, so a config could be saved claiming ``metric`` over a four column
    result and still look right. Replay re-derives instead of trusting it.
    """
    config = InsightConfig(
        id="ins-test-wide-metric",
        title="Wide result",
        generated_sql="SELECT SUM(amount) AS a_amount, COUNT(*) AS b_count, "
                      "AVG(amount) AS c_amount FROM deals",
        viz=VizSpec(type="metric", y="a_amount", unit="$"),
    )
    rendered = app_context.engine.render(config, scope_rep)
    assert rendered.ok
    assert config.viz.type == "table"


def test_incompatible_model_suggestion_is_ignored():
    frame = pd.DataFrame({"a": list("abcdefgh"), "v": [float(i) for i in range(8)]})
    # 8 slices is not a part-to-whole; the deterministic pick must win.
    assert viz.select(frame, "donut").type != "donut"


def test_compatible_model_suggestion_is_honoured():
    frame = pd.DataFrame({"a": list("abc"), "v": [1.0, 2.0, 3.0]})
    assert viz.select(frame, "donut").type == "donut"


# -- versioning -------------------------------------------------------------------------

def test_edit_appends_a_version_and_preserves_the_parent(app_context):
    store = app_context.store
    config = store.get("insight.pipeline_by_stage")
    original_sql = config.generated_sql
    original_version = config.version

    changed = InsightConfig.from_json(config.to_json())
    changed.generated_sql = original_sql + "\nLIMIT 2"
    store.save_version(changed, "test edit")

    head = store.get("insight.pipeline_by_stage")
    assert head.version == original_version + 1
    assert head.change_note == "test edit"

    parent = store.get_version("insight.pipeline_by_stage", original_version)
    assert parent.generated_sql == original_sql

    restored = store.restore("insight.pipeline_by_stage", original_version)
    assert restored.generated_sql == original_sql
    assert len(store.versions("insight.pipeline_by_stage")) >= 3


# -- the stat card ------------------------------------------------------------------------

def test_created_stat_card_shows_the_same_movement_a_kpi_tile_does(app_context, scope_rep):
    """One number plus its baseline renders as a tile with a delta, not a bare value."""
    from intellia.components.insights import _insight_metric

    config = InsightConfig(
        id="ins-test-mom",
        title="Pipeline created",
        generated_sql=(
            "SELECT COALESCE(SUM(CASE WHEN created_date BETWEEN '2026-08-01' "
            "  AND '2026-08-31' THEN amount END), 0) AS pipeline_created, "
            "       COALESCE(SUM(CASE WHEN created_date BETWEEN '2026-07-01' "
            "  AND '2026-07-31' THEN amount END), 0) AS prior_month_pipeline_created "
            "FROM deals"),
        viz=VizSpec(type="metric", unit="$"),
    )
    rendered = app_context.engine.render(config, scope_rep)
    assert rendered.ok and config.viz.compare == "prior_month_pipeline_created"

    value, delta, direction = _insight_metric(config, rendered)
    assert value.startswith("$")
    assert delta.endswith("MoM") and delta[0] in "+-"
    assert direction in ("up", "down")


def test_a_created_stat_card_is_registered_as_one(app_context):
    """The canvas splits the stat band on this, so it has to survive the round trip."""
    from intellia.bootstrap import refresh_insight_widgets

    config = InsightConfig(
        id="ins-test-registry",
        title="Open deal count",
        subtitle="How many deals are open right now.",
        generated_sql="SELECT COUNT(*) AS open_deals FROM deals",
        viz=VizSpec(type="metric", y="open_deals", unit="#"),
        personas=["rep"],
    )
    app_context.store.save_new(config)
    try:
        refresh_insight_widgets(app_context.registry, app_context.store)
        spec = app_context.registry.get("ins-test-registry")
        assert spec.kind == "insight" and spec.viz_type == "metric"
    finally:
        app_context.store.delete("ins-test-registry")
        refresh_insight_widgets(app_context.registry, app_context.store)
        app_context.registry.unregister("ins-test-registry")


# -- card wording -------------------------------------------------------------------------

def test_subtitle_is_cut_to_one_short_clause():
    """The exact description that rendered twice, at full model length, on a tile."""
    assert short_sentence(
        "Total pipeline generated in Q3 2026 (created_date basis), plus "
        "month-over-month comparison between the current month and prior month."
    ) == "Total pipeline generated in Q3 2026."


@pytest.mark.parametrize("subtitle", [
    "Open pipeline value at each stage of the sales process.",
    "New pipeline generated each month, on a created-date cohort.",
    "Open deals that have not moved stage in three weeks or more.",
])
def test_builtin_subtitles_pass_through_untouched(subtitle):
    assert short_sentence(subtitle) == subtitle


def test_every_builtin_subtitle_already_fits_the_card(app_context):
    for config in app_context.store.list_all():
        if config.metadata.source != "builtin":
            continue
        assert short_sentence(config.subtitle) == config.subtitle, config.id


def test_stale_fingerprint_is_detected(app_context):
    config = app_context.store.get("insight.pipeline_by_stage")
    config.schema_fingerprint = "deadbeef"
    assert app_context.engine.is_stale(config) is True
