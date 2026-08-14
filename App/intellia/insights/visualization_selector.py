"""Visualization selection -- deterministic first.

The result shape decides the chart. The model's suggestion is accepted only when
it is compatible with the actual columns; otherwise the deterministic pick wins
and the disagreement is logged. That is what keeps replay stable: the same saved
config always renders the same way.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

import pandas as pd

from intellia.models.insight import ColumnSpec, VizSpec
from intellia.utils.logging import get_logger

log = get_logger("viz")

MONEY_HINTS = ("amount", "pipeline", "bookings", "arr", "revenue", "value", "quota",
               "target", "cost", "deal_size")
PERCENT_HINTS = ("rate", "pct", "percent", "attainment", "share", "margin")
RATIO_HINTS = ("coverage", "ratio", "multiple")
TEMPORAL_HINTS = ("date", "month", "quarter", "week", "day", "period", "time")
ID_HINTS = ("_id", "id_")


def _has_hint(column: str, hints: Tuple[str, ...]) -> bool:
    """Match a hint against whole words in a snake_case column name.

    A raw substring test reads "quarter_pipeline_generated" as a percentage,
    because *gene-rate-d* contains "rate", and "shared_accounts" the same way via
    "share". That column then formats a six figure sum as a percent and, being
    the wrong unit, loses the headline slot to whatever came after it. Padding
    both sides with the separator makes a hint match a word and not a fragment of
    one, and multi-word hints like "deal_size" still match.
    """
    padded = "_" + re.sub(r"[^a-z0-9]+", "_", str(column).lower()).strip("_") + "_"
    return any("_{}_".format(h.strip("_")) in padded for h in hints)


def infer_unit(column: str, series: Optional[pd.Series] = None) -> str:
    if _has_hint(column, PERCENT_HINTS):
        return "%"
    if _has_hint(column, RATIO_HINTS):
        return "x"
    if _has_hint(column, MONEY_HINTS):
        return "$"
    return "#"


def _is_temporal(column: str, series: pd.Series) -> bool:
    if _has_hint(column, TEMPORAL_HINTS):
        if pd.api.types.is_numeric_dtype(series):
            # A raw year/count column named "month" is still a dimension.
            return series.dropna().between(1900, 2999).all() if len(series) else False
        sample = series.dropna().astype(str).head(5).tolist()
        return all(re.match(r"^\d{4}(-\d{2})?(-\d{2})?", s) for s in sample) if sample else True
    return False


def classify_columns(frame: pd.DataFrame) -> List[ColumnSpec]:
    specs: List[ColumnSpec] = []
    for column in frame.columns:
        series = frame[column]
        name = str(column)
        if _has_hint(name, ID_HINTS):
            role = "id"
        elif _is_temporal(name, series):
            role = "temporal"
        elif pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series):
            role = "measure"
        else:
            role = "dimension"
        specs.append(ColumnSpec(
            name=name,
            sqlite_type=str(series.dtype),
            role=role,
            unit=infer_unit(name, series) if role == "measure" else "#",
        ))
    return specs


COUNT_HINTS = ("count", "deals", "num_", "n_", "records", "rows", "meetings",
               "activities", "tasks")

# A value measure outranks a count. Ask "pipeline by stage" and the query often
# returns both SUM(amount) and COUNT(*); charting the count answers a different
# question than the prose does, and the two then contradict each other on screen.
UNIT_RANK = {"$": 0, "%": 1, "x": 2, "#": 3}

# A period comparison is a second measure that exists only to be moved against.
# "prior" carries a value in the same unit; "change" carries the movement itself.
PRIOR_HINTS = ("prior", "previous", "prev", "last_month", "last_quarter",
               "last_year", "last_period", "baseline")
CHANGE_HINTS = ("mom", "qoq", "yoy", "change", "delta", "growth")

PERIOD_LABELS = (("mom", "MoM"), ("month", "MoM"), ("qoq", "QoQ"),
                 ("quarter", "QoQ"), ("yoy", "YoY"), ("year", "YoY"))


def comparison_kind(column: str) -> str:
    """"prior", "change" or "" -- what a second measure on a one-row result is."""
    if _has_hint(column, PRIOR_HINTS):
        return "prior"
    if _has_hint(column, CHANGE_HINTS):
        return "change"
    return ""


def _period_label(column: str) -> str:
    name = str(column).lower()
    for token, label in PERIOD_LABELS:
        if token in name:
            return label
    return "vs prior"


def _measure_rank(measure: ColumnSpec, position: int) -> Tuple[int, int, int, int]:
    # The comparison flag comes first: a baseline is never the headline number,
    # whatever its unit, so "deal_count plus prior_pipeline" cannot chart the
    # baseline just because dollars outrank counts.
    looks_like_count = _has_hint(measure.name, COUNT_HINTS)
    is_comparison = 1 if comparison_kind(measure.name) else 0
    return (is_comparison, UNIT_RANK.get(measure.unit, 3),
            1 if looks_like_count else 0, position)


def _split(specs: List[ColumnSpec]) -> Tuple[List[ColumnSpec], List[ColumnSpec], List[ColumnSpec]]:
    measures = [c for c in specs if c.role == "measure"]
    measures = [m for _, m in sorted(
        ((_measure_rank(m, i), m) for i, m in enumerate(measures)),
        key=lambda pair: pair[0])]
    temporal = [c for c in specs if c.role == "temporal"]
    dimensions = [c for c in specs if c.role == "dimension"]
    return measures, temporal, dimensions


def _is_metric_shape(measures: List[ColumnSpec]) -> bool:
    """One number, optionally with one baseline to move against.

    Three unrelated measures on one row is a table, not a stat tile: the card can
    only show one of them and silently dropping the other two reads as a bug.
    """
    if len(measures) == 1:
        return True
    return len(measures) == 2 and bool(comparison_kind(measures[1].name))


def _attach_comparison(viz: VizSpec, rest: List[ColumnSpec]) -> None:
    viz.compare, viz.compare_kind, viz.delta_label = None, "", ""
    if not rest:
        return
    kind = comparison_kind(rest[0].name)
    if not kind:
        return
    viz.compare = rest[0].name
    viz.compare_kind = kind
    viz.delta_label = _period_label(rest[0].name)


def select(frame: pd.DataFrame, suggested: str = "",
           specs: Optional[List[ColumnSpec]] = None) -> VizSpec:
    """Pick the visualization from the data's actual shape."""
    specs = specs or classify_columns(frame)
    measures, temporal, dimensions = _split(specs)
    rows = len(frame)

    viz = VizSpec(type="table")

    if rows == 0:
        viz.type = "table"
    elif rows == 1 and not dimensions and not temporal and _is_metric_shape(measures):
        viz.type = "metric"
        viz.y = measures[0].name
        viz.unit = measures[0].unit
        _attach_comparison(viz, measures[1:])
    elif temporal and measures:
        viz.type = "line"
        viz.x = temporal[0].name
        viz.y = measures[0].name
        viz.unit = measures[0].unit
    elif dimensions and len(measures) >= 1 and rows <= 25:
        # Horizontal bars keep long account and rep names readable.
        viz.type = "hbar"
        viz.x = measures[0].name
        viz.y = dimensions[0].name
        viz.unit = measures[0].unit
        viz.sort = "-x"
        viz.limit = 15
    else:
        viz.type = "table"
        if measures:
            viz.unit = measures[0].unit

    if suggested:
        viz = _reconcile(viz, suggested, specs, rows)
    return viz


def _reconcile(deterministic: VizSpec, suggested: str,
               specs: List[ColumnSpec], rows: int) -> VizSpec:
    """Honour the model's choice only where the data actually supports it."""
    suggestion = (suggested or "").strip().lower()
    if suggestion in ("", deterministic.type):
        return deterministic

    measures, temporal, dimensions = _split(specs)
    compatible = {
        "metric": rows == 1 and _is_metric_shape(measures),
        "bar": bool(dimensions and measures),
        "hbar": bool(dimensions and measures),
        "line": bool((temporal or dimensions) and measures),
        "area": bool((temporal or dimensions) and measures),
        "donut": bool(dimensions and measures and 2 <= rows <= 6),
        "funnel": bool(dimensions and measures and rows <= 8),
        "table": True,
        "list": True,
    }
    if not compatible.get(suggestion, False):
        log.info("Ignoring incompatible viz suggestion %r; using %r",
                 suggestion, deterministic.type)
        return deterministic

    out = VizSpec(**vars(deterministic))
    out.type = suggestion
    if suggestion in ("bar", "donut", "funnel"):
        out.x = dimensions[0].name if dimensions else out.x
        out.y = measures[0].name if measures else out.y
        out.unit = measures[0].unit if measures else out.unit
    elif suggestion in ("line", "area"):
        out.x = (temporal[0].name if temporal
                 else dimensions[0].name if dimensions else out.x)
        out.y = measures[0].name if measures else out.y
        out.unit = measures[0].unit if measures else out.unit
    elif suggestion == "metric" and measures:
        out.y = measures[0].name
        out.unit = measures[0].unit
        _attach_comparison(out, measures[1:])
    return out
